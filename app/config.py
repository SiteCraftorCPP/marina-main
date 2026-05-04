from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional

from dotenv import load_dotenv


def _parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        ids.add(int(part))
    return ids


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: set[int]
    db_path: str
    parse_mode: str
    question_delay_sec: float
    # BePaid hosted checkout (https://checkout.bepaid.by/ctp/api/checkouts)
    bepaid_shop_id: str
    bepaid_secret_key: str
    bepaid_test: bool
    payment_amount: int
    payment_currency: str
    public_base_url: str
    # Срок жизни checkout-токена (минуты). None / 0 — не передаём expired_at, берётся дефолт BePaid.
    checkout_expires_minutes: Optional[int]

    @property
    def bepaid_enabled(self) -> bool:
        return bool(self.bepaid_shop_id and self.bepaid_secret_key and self.public_base_url)


def load_config() -> Config:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required (set it in .env)")

    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))
    db_path = os.getenv("DB_PATH", "bot.db").strip() or "bot.db"
    parse_mode = (os.getenv("PARSE_MODE", "HTML") or "HTML").strip()
    question_delay_sec = float(os.getenv("QUESTION_DELAY_SEC", "0") or "0")

    bepaid_shop_id = (os.getenv("BEPAID_SHOP_ID", "") or "").strip()
    bepaid_secret_key = os.getenv("BEPAID_SECRET_KEY", "") or ""
    bepaid_test_raw = (os.getenv("BEPAID_TEST", "true") or "true").strip().lower()
    bepaid_test = bepaid_test_raw in ("1", "true", "yes", "on")

    payment_amount_raw = (os.getenv("PAYMENT_AMOUNT", "1") or "1").strip()
    try:
        payment_amount = int(payment_amount_raw)
    except ValueError:
        payment_amount = 1

    payment_currency = (os.getenv("PAYMENT_CURRENCY", "BYN") or "BYN").strip().upper()

    public_base_url = (os.getenv("PUBLIC_BASE_URL", "") or "").strip().rstrip("/")

    ttl_raw = (os.getenv("CHECKOUT_EXPIRES_MINUTES", "") or "").strip()
    checkout_expires_minutes: Optional[int] = None
    if ttl_raw:
        try:
            v = int(ttl_raw)
            checkout_expires_minutes = v if v > 0 else None
        except ValueError:
            checkout_expires_minutes = None

    return Config(
        bot_token=bot_token,
        admin_ids=admin_ids,
        db_path=db_path,
        parse_mode=parse_mode,
        question_delay_sec=question_delay_sec,
        bepaid_shop_id=bepaid_shop_id,
        bepaid_secret_key=bepaid_secret_key,
        bepaid_test=bepaid_test,
        payment_amount=payment_amount,
        payment_currency=payment_currency,
        public_base_url=public_base_url,
        checkout_expires_minutes=checkout_expires_minutes,
    )

