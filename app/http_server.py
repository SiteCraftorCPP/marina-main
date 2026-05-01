from __future__ import annotations

import json
import logging

from aiogram import Bot
from aiohttp import web

from .bepaid_api import (
    extract_amount_currency,
    extract_uid,
    is_transaction_successful,
    normalize_webhook_transaction,
    resolve_tracking_id,
    verify_notification_basic_auth,
)
from .config import Config
from .db import Database
from .keyboards import kb_channel

logger = logging.getLogger("bot.http")


def _html(body: str) -> web.Response:
    html = (
        "<!doctype html><html lang='ru'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<body style='font-family:system-ui;padding:24px'>{body}</body></html>"
    )
    return web.Response(text=html, content_type="text/html; charset=utf-8")


async def health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def payment_stub(_request: web.Request) -> web.Response:
    return _html("<p>Можно вернуться в Telegram и дождаться сообщения от бота.</p>")


async def bepaid_webhook(request: web.Request) -> web.Response:
    cfg: Config = request.app["cfg"]
    db: Database = request.app["db"]
    bot: Bot = request.app["bot"]

    if not cfg.bepaid_enabled:
        return web.Response(status=503)

    if not verify_notification_basic_auth(request.headers, cfg):
        return web.Response(status=401)

    raw = await request.read()
    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception:
        logger.warning("bepaid webhook: invalid JSON raw_len=%s", len(raw))
        return web.Response(status=400)

    if not isinstance(body, dict):
        return web.Response(status=400)

    tx = normalize_webhook_transaction(body)
    if tx is None:
        # Другие типы уведомлений (истёкший token checkout, подписки и т.д.) — ACK 200.
        logger.info(
            "bepaid webhook ignored (shape): keys=%s",
            list(body.keys())[:40],
        )
        return web.Response(status=200)

    if not is_transaction_successful(tx):
        # pending/failed/expired — ACK 200 (см. retry schedule в доке BePaid).
        return web.Response(status=200)

    tracking_id = resolve_tracking_id(body, tx)
    if not tracking_id:
        logger.warning("bepaid webhook: missing tracking_id keys=%s", list(body.keys())[:30])
        return web.Response(status=200)

    uid = extract_uid(tx)
    amount, currency = extract_amount_currency(tx)

    user_id = await db.try_complete_payment(
        tracking_id=tracking_id,
        transaction_uid=uid,
        amount=amount,
        currency=currency,
    )
    if user_id is None:
        return web.Response(status=200)

    channel_url = await db.get_setting("channel_url")
    text = (
        "<b>Оплата получена.</b>\n\n"
        "Ниже — доступ в закрытый канал. Это единоразовый доступ без ежемесячного списания.\n\n"
        "Если ссылка не открывается — напишите в поддержку и приложите скрин оплаты."
    )

    try:
        await bot.send_message(user_id, text, reply_markup=kb_channel(channel_url))
        await db.add_event(user_id, "payment_success")
        await db.set_clicked_buy(user_id)
    except Exception:
        logger.exception("failed to notify user_id=%s after payment tracking_id=%s", user_id, tracking_id)

    return web.Response(status=200)


def create_app(*, bot: Bot, db: Database, cfg: Config) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app["db"] = db
    app["cfg"] = cfg

    app.router.add_get("/health", health)
    app.router.add_get("/payment/return", payment_stub)
    app.router.add_get("/payment/success", payment_stub)
    app.router.add_get("/payment/decline", payment_stub)
    app.router.add_get("/payment/fail", payment_stub)
    app.router.add_get("/payment/cancel", payment_stub)
    app.router.add_post("/webhooks/bepaid", bepaid_webhook)
    return app
