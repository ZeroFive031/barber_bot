"""Клавиатуры и данные для кнопок."""
from datetime import date, datetime

from aiogram.filters.callback_data import CallbackData
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

BTN_BOOK = "📅 Записаться"
BTN_MY = "🗂 Мои записи"


# CallbackData — типизированные данные кнопок. Вместо разбора строк вида
# "svc_3" вручную aiogram сам упакует и распакует поля.
# Разделитель внутри — двоеточие, поэтому время храним как "1400", а не "14:00".
class ServiceCb(CallbackData, prefix="svc"):
    id: int


class DayCb(CallbackData, prefix="day"):
    day: str  # YYYY-MM-DD


class TimeCb(CallbackData, prefix="time"):
    hhmm: str  # 1400


class ConfirmCb(CallbackData, prefix="ok"):
    yes: bool


class CancelCb(CallbackData, prefix="cancel"):
    id: int


class BackCb(CallbackData, prefix="back"):
    to: str  # services / days


class AdminDayCb(CallbackData, prefix="aday"):
    day: str


class AdminCancelCb(CallbackData, prefix="acancel"):
    id: int


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_BOOK), KeyboardButton(text=BTN_MY)]],
        resize_keyboard=True,
    )


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def services_kb(services):
    kb = InlineKeyboardBuilder()
    for s in services:
        kb.button(text=f"{s['name']} — {s['price']} ₽", callback_data=ServiceCb(id=s["id"]))
    kb.adjust(1)
    return kb.as_markup()


def day_label(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]} {d:%d.%m}"


def days_kb(days: list[date]):
    kb = InlineKeyboardBuilder()
    for d in days:
        kb.button(text=day_label(d), callback_data=DayCb(day=d.isoformat()))
    kb.button(text="← Назад", callback_data=BackCb(to="services"))
    kb.adjust(3)
    return kb.as_markup()


def times_kb(slots: list[datetime]):
    kb = InlineKeyboardBuilder()
    for s in slots:
        kb.button(text=f"{s:%H:%M}", callback_data=TimeCb(hhmm=f"{s:%H%M}"))
    kb.button(text="← Другой день", callback_data=BackCb(to="days"))
    kb.adjust(4)
    return kb.as_markup()


def confirm_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=ConfirmCb(yes=True))
    kb.button(text="✖️ Отмена", callback_data=ConfirmCb(yes=False))
    return kb.as_markup()


def my_bookings_kb(bookings):
    kb = InlineKeyboardBuilder()
    for b in bookings:
        kb.button(text=f"Отменить {b.start_at[5:]}", callback_data=CancelCb(id=b.id))
    kb.adjust(1)
    return kb.as_markup()


def admin_days_kb(days: list[date]):
    kb = InlineKeyboardBuilder()
    for d in days:
        kb.button(text=day_label(d), callback_data=AdminDayCb(day=d.isoformat()))
    kb.adjust(3)
    return kb.as_markup()


def admin_bookings_kb(bookings):
    kb = InlineKeyboardBuilder()
    for b in bookings:
        kb.button(text=f"✖️ {b.start_at[11:]} {b.service}", callback_data=AdminCancelCb(id=b.id))
    kb.adjust(1)
    return kb.as_markup()
