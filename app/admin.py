from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.types import BufferedInputFile
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import Config
from .db import Database
from .keyboards import ADMIN_BUTTON_TEXT, kb_admin_reply
from .logic import validate_channel_url


logger = logging.getLogger("bot.admin")
admin_router = Router()

_pending_setting_by_user: dict[int, str] = {}


def is_admin(user_id: int, cfg: Config) -> bool:
    return user_id in cfg.admin_ids


def kb_admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Изменить приветственное сообщение", callback_data="admin:set:welcome_message")],
            [InlineKeyboardButton(text="Изменить сообщение о продаже курса", callback_data="admin:set:sale_message")],
            [InlineKeyboardButton(text="Изменить ссылку на канал", callback_data="admin:set:channel_url")],
            [InlineKeyboardButton(text="Статистика", callback_data="admin:stats")],
            [InlineKeyboardButton(text="Выгрузка пользователей (CSV)", callback_data="admin:export")],
        ]
    )


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message, cfg: Config) -> None:
    u = message.from_user
    if not u or not is_admin(u.id, cfg):
        return
    await message.answer("<b>Админ-панель</b>", reply_markup=kb_admin_menu())


@admin_router.message(F.text == ADMIN_BUTTON_TEXT)
async def on_admin_button(message: Message, cfg: Config) -> None:
    """Нажатие на постоянную reply-кнопку «🛠 АДМИНКА»."""
    u = message.from_user
    if not u or not is_admin(u.id, cfg):
        return
    # сбрасываем возможный «ожидающий ввод» режим, если админ передумал
    _pending_setting_by_user.pop(u.id, None)
    await message.answer(
        "<b>Админ-панель</b>",
        reply_markup=kb_admin_menu(),
    )
    # на всякий случай переотправляем reply-клавиатуру (если её случайно скрыли)
    await message.answer("Кнопка «АДМИНКА» закреплена ниже.", reply_markup=kb_admin_reply())


@admin_router.callback_query(F.data == "admin:menu")
async def cb_menu(cb: CallbackQuery, cfg: Config) -> None:
    u = cb.from_user
    if not u or not cb.message or not is_admin(u.id, cfg):
        return
    await cb.answer()
    await cb.message.answer("<b>Админ-панель</b>", reply_markup=kb_admin_menu())


@admin_router.callback_query(F.data.startswith("admin:set:"))
async def cb_set(cb: CallbackQuery, db: Database, cfg: Config) -> None:
    u = cb.from_user
    if not u or not cb.message or not is_admin(u.id, cfg):
        return

    key = (cb.data or "").split("admin:set:", 1)[1].strip()
    if key not in ("welcome_message", "sale_message", "channel_url"):
        await cb.answer("Неизвестный ключ.", show_alert=True)
        return

    current = await db.get_setting(key)  # type: ignore[arg-type]

    await cb.answer()
    await cb.message.answer(
        f"<b>Текущие настройки</b>\n\n<b>{key}</b>:\n{current}\n\n"
        "Отправьте новым сообщением новый текст/ссылку."
    )
    _pending_setting_by_user[u.id] = key
    logger.info("admin pending set user_id=%s key=%s", u.id, key)


@admin_router.message()
async def admin_text_catcher(message: Message, db: Database, cfg: Config) -> None:
    u = message.from_user
    if not u or not is_admin(u.id, cfg):
        return

    key = _pending_setting_by_user.get(u.id)
    if not key:
        return

    new_value = (message.html_text or message.text or "").strip()
    if not new_value:
        await message.answer("Пустое значение не сохранено.", reply_markup=kb_admin_menu())
        _pending_setting_by_user.pop(u.id, None)
        return

    if key == "channel_url" and not validate_channel_url(new_value):
        await message.answer("Некорректная ссылка. Пришлите URL вида `https://t.me/...`.", reply_markup=kb_admin_menu())
        return

    await db.set_setting(key, new_value)  # type: ignore[arg-type]
    _pending_setting_by_user.pop(u.id, None)

    await message.answer(f"Сохранено: <b>{key}</b> обновлено.", reply_markup=kb_admin_menu())
    logger.info("admin setting updated user_id=%s key=%s", u.id, key)


@admin_router.callback_query(F.data == "admin:stats")
async def cb_stats(cb: CallbackQuery, db: Database, cfg: Config) -> None:
    u = cb.from_user
    if not u or not cb.message or not is_admin(u.id, cfg):
        return

    s = await db.stats()
    by_type = s.get("by_type", {})
    text = (
        "<b>Статистика</b>\n\n"
        f"Пользователей всего: <b>{s['users_total']}</b>\n"
        f"Прошли тест: <b>{s['completed_total']}</b>\n"
        f"Нажали «Купить»: <b>{s['clicked_buy_total']}</b>\n"
        f"Нажали «Перейти в канал»: <b>{s['clicked_channel_total']}</b>\n\n"
        "<b>Распределение по типам:</b>\n"
        f"A: <b>{by_type.get('A', 0)}</b>\n"
        f"B: <b>{by_type.get('B', 0)}</b>\n"
        f"C: <b>{by_type.get('C', 0)}</b>\n"
        f"D: <b>{by_type.get('D', 0)}</b>\n"
    )
    await cb.answer()
    await cb.message.answer(text, reply_markup=kb_admin_menu())


@admin_router.callback_query(F.data == "admin:export")
async def cb_export(cb: CallbackQuery, db: Database, cfg: Config) -> None:
    u = cb.from_user
    if not u or not cb.message or not is_admin(u.id, cfg):
        return

    csv_text = await db.export_users_csv()
    f = BufferedInputFile(csv_text.encode("utf-8"), filename="users.csv")
    await cb.answer()
    await cb.message.answer_document(f, caption="Выгрузка пользователей (CSV)")
