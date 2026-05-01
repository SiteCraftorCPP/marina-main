from __future__ import annotations

import asyncio
import logging
import os
import uuid

import aiohttp
from aiohttp import web

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from .admin import admin_router, is_admin
from .bepaid_api import create_hosted_checkout
from .config import Config, load_config
from .content import QUESTIONS, RESULTS, TEST_INSTRUCTION, TEST_SUBTITLE, TEST_TITLE, TYPE_NAMES
from .db import Database
from .http_server import create_app
from .keyboards import kb_admin_reply, kb_buy, kb_channel, kb_pay_link, kb_question, kb_restart, kb_start
from .logic import compute_result


logger = logging.getLogger("bot")


def _format_question(q_idx: int) -> str:
    q = QUESTIONS[q_idx]
    return f"<b>Вопрос {q_idx + 1} из {len(QUESTIONS)}</b>\n{q.text}"


async def send_question(message: Message, db: Database, user_id: int, cfg: Config, q_idx: int) -> None:
    if q_idx < 0 or q_idx >= len(QUESTIONS):
        return
    if cfg.question_delay_sec > 0:
        await asyncio.sleep(cfg.question_delay_sec)
    q = QUESTIONS[q_idx]
    await message.answer(_format_question(q_idx), reply_markup=kb_question(q_idx, q))


async def send_welcome(message: Message, db: Database) -> None:
    welcome = await db.get_setting("welcome_message")
    intro = (
        f"<b>{TEST_TITLE}</b>\n\n"
        f"{TEST_SUBTITLE}\n\n"
        f"{TEST_INSTRUCTION}\n\n"
        f"{welcome}"
    )
    await message.answer(intro, reply_markup=kb_start())


class HttpSessionMiddleware(BaseMiddleware):
    def __init__(self, session: aiohttp.ClientSession) -> None:
        super().__init__()
        self._session = session

    async def __call__(self, handler, event, data):
        data["http"] = self._session
        return await handler(event, data)


router = Router()


class DbConfigMiddleware(BaseMiddleware):
    def __init__(self, db: Database, cfg: Config) -> None:
        super().__init__()
        self._db = db
        self._cfg = cfg

    async def __call__(self, handler, event, data):
        data["db"] = self._db
        data["cfg"] = self._cfg
        return await handler(event, data)


@router.message(Command("start"))
async def cmd_start(message: Message, db: Database, cfg: Config) -> None:
    u = message.from_user
    if not u:
        return
    await db.upsert_user(u.id, u.username, u.first_name)
    await db.reset_session(u.id)
    logger.info("start user_id=%s username=%s", u.id, u.username)

    # Для админа — закрепляем reply-кнопку «АДМИНКА» под полем ввода.
    if is_admin(u.id, cfg):
        await message.answer("Админ-режим включён.", reply_markup=kb_admin_reply())

    await send_welcome(message, db)


@router.callback_query(F.data == "start_test")
async def cb_start_test(cb: CallbackQuery, db: Database, cfg: Config) -> None:
    u = cb.from_user
    if not u or not cb.message:
        return
    await db.upsert_user(u.id, u.username, u.first_name)
    await db.reset_session(u.id)
    await cb.answer()
    logger.info("start_test user_id=%s", u.id)
    await send_question(cb.message, db, u.id, cfg, 0)


@router.callback_query(F.data == "restart")
async def cb_restart(cb: CallbackQuery, db: Database, cfg: Config) -> None:
    u = cb.from_user
    if not u or not cb.message:
        return
    await db.reset_session(u.id)
    await cb.answer()
    logger.info("restart user_id=%s", u.id)
    await send_question(cb.message, db, u.id, cfg, 0)


@router.callback_query(F.data.startswith("ans:"))
async def cb_answer(cb: CallbackQuery, db: Database, cfg: Config) -> None:
    u = cb.from_user
    if not u or not cb.message:
        return

    try:
        _, q_idx_s, letter = (cb.data or "").split(":")
        q_idx = int(q_idx_s)
        letter = letter.strip().upper()
    except Exception:
        await cb.answer("Некорректный ответ.", show_alert=True)
        return

    user = await db.get_user(u.id)
    if not user:
        await db.upsert_user(u.id, u.username, u.first_name)
        await db.reset_session(u.id)
        user = await db.get_user(u.id)

    # protect against double-taps / stale callbacks
    if user and user.current_question != q_idx:
        await cb.answer("Ответ уже принят. Продолжаем.", show_alert=False)
        return

    await db.append_answer(u.id, letter)
    await cb.answer()
    logger.info("answer user_id=%s q=%s letter=%s", u.id, q_idx + 1, letter)

    next_q = q_idx + 1
    if next_q < len(QUESTIONS):
        await send_question(cb.message, db, u.id, cfg, next_q)
        return

    updated = await db.get_user(u.id)
    if not updated:
        return

    res = compute_result(updated.count_a, updated.count_b, updated.count_c, updated.count_d)
    primary_text = RESULTS[res.primary]
    await db.set_completed(u.id, res.primary)

    if res.secondary:
        secondary_name = TYPE_NAMES[res.secondary]
        secondary_short = (
            f"\n\n<b>Также вам близок тип:</b> {secondary_name}\n"
            "Это тоже заметно в ваших реакциях и сценариях — особенно в напряжённых моментах."
        )
        await cb.message.answer(primary_text + secondary_short, reply_markup=kb_restart())
    else:
        await cb.message.answer(primary_text, reply_markup=kb_restart())

    # Sale message (separate)
    sale = await db.get_setting("sale_message")
    await cb.message.answer(sale, reply_markup=kb_buy())


@router.callback_query(F.data == "buy")
async def cb_buy(cb: CallbackQuery, db: Database, cfg: Config, http: aiohttp.ClientSession) -> None:
    u = cb.from_user
    if not u or not cb.message:
        return

    await db.upsert_user(u.id, u.username, u.first_name)
    user = await db.get_user(u.id)
    if not user:
        return

    if user.paid_access:
        await cb.answer()
        url = await db.get_setting("channel_url")
        await cb.message.answer(
            "У вас уже есть доступ. Нажмите кнопку ниже, чтобы перейти в закрытый канал:",
            reply_markup=kb_channel(url),
        )
        logger.info("buy already_paid user_id=%s", u.id)
        return

    await db.set_clicked_buy(u.id)
    await db.add_event(u.id, "buy_click")

    if not cfg.bepaid_enabled:
        await cb.answer("Оплата не настроена.", show_alert=True)
        await cb.message.answer(
            "Оплата временно недоступна (не заданы переменные BePaid / PUBLIC_BASE_URL). "
            "Напишите администратору."
        )
        logger.warning("buy clicked but bepaid_enabled=false user_id=%s", u.id)
        return

    tracking_id = f"{u.id}-{uuid.uuid4().hex}"
    await db.create_payment(tracking_id, u.id, cfg.payment_amount, cfg.payment_currency)

    try:
        pay_url = await create_hosted_checkout(
            http,
            cfg,
            tracking_id=tracking_id,
            first_name=u.first_name,
        )
    except Exception:
        logger.exception("checkout failed user_id=%s tracking_id=%s", u.id, tracking_id)
        await cb.answer("Не удалось создать оплату.", show_alert=True)
        await cb.message.answer("Не удалось создать платёж. Попробуйте позже или напишите администратору.")
        return

    await cb.answer()
    logger.info("checkout_created user_id=%s tracking_id=%s", u.id, tracking_id)
    await cb.message.answer(
        "<b>Оплата</b>\n\n"
        "Нажмите кнопку ниже, завершите оплату в BePaid и вернитесь в Telegram — "
        "бот пришлёт ссылку на закрытый канал после успешной оплаты.",
        reply_markup=kb_pay_link(pay_url),
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    cfg = load_config()
    db = Database(cfg.db_path)
    await db.init()

    parse_mode = ParseMode.HTML if cfg.parse_mode.upper() == "HTML" else None
    bot = Bot(
        token=cfg.bot_token,
        default=DefaultBotProperties(parse_mode=parse_mode) if parse_mode else None,
    )
    dp = Dispatcher()

    mw = DbConfigMiddleware(db, cfg)
    dp.update.outer_middleware(mw)

    dp.include_router(router)
    dp.include_router(admin_router)

    port = int(os.getenv("PORT", "8080"))
    http_app = create_app(bot=bot, db=db, cfg=cfg)
    runner = web.AppRunner(http_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("http listening on 0.0.0.0:%s", port)

    try:
        async with aiohttp.ClientSession() as http_session:
            dp.update.outer_middleware(HttpSessionMiddleware(http_session))
            await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
