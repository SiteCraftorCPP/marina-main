from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from .content import Question


ADMIN_BUTTON_TEXT = "🛠 АДМИНКА"


def kb_admin_reply() -> ReplyKeyboardMarkup:
    """Постоянная reply-кнопка под полем ввода — только для админов."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=ADMIN_BUTTON_TEXT)]],
        resize_keyboard=True,
        is_persistent=True,
    )


def kb_remove_reply() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def kb_start() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Начать тест", callback_data="start_test")],
        ]
    )


def kb_question(q_idx: int, q: Question) -> InlineKeyboardMarkup:
    # callback: ans:<q_idx>:<letter>
    rows = []
    for opt in q.options:
        rows.append([InlineKeyboardButton(text=opt.text, callback_data=f"ans:{q_idx}:{opt.letter}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_buy() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Купить", callback_data="buy")],
        ]
    )


def kb_channel(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Перейти в канал", url=url)],
        ]
    )


def kb_pay_link(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Перейти к оплате", url=url)],
        ]
    )


def kb_restart() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пройти тест заново", callback_data="restart")],
        ]
    )

