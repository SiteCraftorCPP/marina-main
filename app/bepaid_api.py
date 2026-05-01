from __future__ import annotations

import base64
import json
import logging
from typing import Any, Optional

import aiohttp
from aiohttp import BasicAuth

from .config import Config

logger = logging.getLogger("bot.bepaid")

CHECKOUT_API_URL = "https://checkout.bepaid.by/ctp/api/checkouts"


def verify_notification_basic_auth(request_headers: Any, cfg: Config) -> bool:
    """Сверяем Authorization с Shop ID / Secret Key (как в доке webhooks)."""
    raw = request_headers.get("Authorization") or request_headers.get("authorization")
    if not raw or not str(raw).startswith("Basic "):
        return False
    try:
        b64 = str(raw).split(" ", 1)[1].strip()
        decoded = base64.b64decode(b64.encode("ascii"), validate=True).decode("utf-8")
        login, _, password = decoded.partition(":")
    except Exception:
        return False
    shop = (cfg.bepaid_shop_id or "").strip()
    secret = cfg.bepaid_secret_key or ""
    return login.strip() == shop and password == secret


def coerce_id(v: Any) -> Optional[str]:
    """tracking_id в JSON может прийти строкой или числом."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return str(int(v))
    if isinstance(v, str):
        s = v.strip()
        return s or None
    return None


def extract_tracking_id(tx: dict[str, Any]) -> Optional[str]:
    return coerce_id(tx.get("tracking_id"))


def resolve_tracking_id(body: dict[str, Any], tx: Optional[dict[str, Any]]) -> Optional[str]:
    """tracking_id может быть в transaction, в корне тела (checkout) или в order."""
    if tx:
        tid = coerce_id(tx.get("tracking_id"))
        if tid:
            return tid
    tid = coerce_id(body.get("tracking_id"))
    if tid:
        return tid
    order = body.get("order")
    if isinstance(order, dict):
        return coerce_id(order.get("tracking_id"))
    return None


def normalize_webhook_transaction(body: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Основной кейс: {"transaction": {...}} (как в доке card transactions / checkout после оплаты).
    Защитный кейс: редкий «плоский» объект с payment/status без обёртки transaction.
    См. https://docs.bepaid.by/en/using_api/webhooks/
    """
    tx = body.get("transaction")
    if isinstance(tx, dict):
        return tx

    pay = body.get("payment")
    st = body.get("status")
    if isinstance(pay, dict) and (st == "successful" or pay.get("status") == "successful"):
        return body
    return None


def is_transaction_successful(tx: dict[str, Any]) -> bool:
    if tx.get("status") == "successful":
        return True
    pay = tx.get("payment")
    if isinstance(pay, dict) and pay.get("status") == "successful":
        return True
    return False


def extract_uid(tx: dict[str, Any]) -> Optional[str]:
    for k in ("uid", "id"):
        v = tx.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def extract_amount_currency(tx: dict[str, Any]) -> tuple[Optional[int], Optional[str]]:
    amount = tx.get("amount")
    currency = tx.get("currency")
    pay = tx.get("payment")
    if isinstance(pay, dict):
        if amount is None:
            amount = pay.get("amount")
        if currency is None:
            currency = pay.get("currency")

    ai: Optional[int] = None
    if amount is not None:
        try:
            ai = int(round(float(amount)))
        except (TypeError, ValueError):
            ai = None

    cs: Optional[str] = None
    if isinstance(currency, str) and currency.strip():
        cs = currency.strip().upper()
    return ai, cs


async def create_hosted_checkout(
    session: aiohttp.ClientSession,
    cfg: Config,
    *,
    tracking_id: str,
    first_name: Optional[str],
) -> str:
    """
    Создаёт hosted checkout, возвращает redirect_url (открыть в браузере / url-кнопка Telegram).
    """
    base = (cfg.public_base_url or "").rstrip("/")
    if not base:
        raise RuntimeError("PUBLIC_BASE_URL is required for BePaid checkout")

    auth = BasicAuth(str(cfg.bepaid_shop_id).strip(), cfg.bepaid_secret_key or "")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-API-Version": "2",
    }

    fn = (first_name or "").strip() or "Клиент"
    customer: dict[str, Any] = {"first_name": fn}

    payload: dict[str, Any] = {
        "checkout": {
            "test": bool(cfg.bepaid_test),
            "transaction_type": "payment",
            "attempts": 3,
            "settings": {
                "return_url": f"{base}/payment/return",
                "success_url": f"{base}/payment/success",
                "decline_url": f"{base}/payment/decline",
                "fail_url": f"{base}/payment/fail",
                "cancel_url": f"{base}/payment/cancel",
                "notification_url": f"{base}/webhooks/bepaid",
                "language": "ru",
            },
            "order": {
                "currency": cfg.payment_currency,
                "amount": int(cfg.payment_amount),
                "description": "Доступ к обучению (единоразово)",
                "tracking_id": tracking_id,
            },
            "customer": customer,
        }
    }

    async with session.post(CHECKOUT_API_URL, json=payload, headers=headers, auth=auth) as resp:
        text = await resp.text()
        if resp.status >= 400:
            logger.error("bepaid checkout HTTP %s body=%s", resp.status, text[:2000])
            raise RuntimeError(f"BePaid checkout failed: HTTP {resp.status}")

        try:
            data = json.loads(text)
        except Exception:
            logger.error("bepaid checkout non-json body=%s", text[:2000])
            raise RuntimeError("BePaid checkout failed: invalid JSON response")

    checkout = data.get("checkout") if isinstance(data, dict) else None
    redirect_url = None
    if isinstance(checkout, dict):
        ru = checkout.get("redirect_url")
        if isinstance(ru, str) and ru.strip():
            redirect_url = ru.strip()

    if not redirect_url:
        logger.error("bepaid checkout unexpected response=%s", str(data)[:2000])
        raise RuntimeError("BePaid checkout failed: no redirect_url")

    return redirect_url
