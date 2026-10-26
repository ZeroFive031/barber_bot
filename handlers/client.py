"""Сценарий клиента: выбор услуги → дня → времени → телефон → подтверждение."""
import logging
import re
from datetime import date, datetime

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

import keyboards as kb
from config import Settings
from db import Database, SlotTaken
from slots import FMT, booking_days, free_slots

router = Router()
log = logging.getLogger(__name__)

PHONE_RE = re.compile(r"^\+?[\d\s\-()]{10,18}$")


class Booking(StatesGroup):
    service = State()
    day = State()
    time = State()
    phone = State()
    confirm = State()


def now_local(settings: Settings) -> datetime:
    # Время салона без tzinfo — в таком же виде оно лежит в базе.
    return datetime.now(settings.tz).replace(tzinfo=None)


# ---------- старт и меню ----------
@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Привет, {message.from_user.first_name}! 💈\n"
        "Я помогу записаться на стрижку. Выбери действие в меню ниже.",
        reply_markup=kb.main_menu(),
    )


@router.message(F.text == kb.BTN_BOOK)
async def book_start(message: Message, state: FSMContext, db: Database):
    await state.clear()
    await state.set_state(Booking.service)
    await message.answer("Выбери услугу:", reply_markup=kb.services_kb(await db.services()))


# ---------- шаг 1: услуга ----------
@router.callback_query(Booking.service, kb.ServiceCb.filter())
async def pick_service(call: CallbackQuery, callback_data: kb.ServiceCb, state: FSMContext,
                       db: Database, settings: Settings):
    service = await db.service(callback_data.id)
    if not service:
        await call.answer("Услуга не найдена", show_alert=True)
        return
    await state.update_data(service_id=service["id"])
    await state.set_state(Booking.day)
    days = booking_days(now_local(settings).date(), settings.days_ahead)
    await call.message.edit_text(f"<b>{service['name']}</b>\nВыбери день:", reply_markup=kb.days_kb(days))
    await call.answer()


# ---------- шаг 2: день ----------
@router.callback_query(Booking.day, kb.DayCb.filter())
async def pick_day(call: CallbackQuery, callback_data: kb.DayCb, state: FSMContext,
                   db: Database, settings: Settings):
    day = date.fromisoformat(callback_data.day)
    slots = free_slots(day, await db.busy_times(callback_data.day), now_local(settings),
                       settings.work_start, settings.work_end, settings.slot_minutes)
    if not slots:
        await call.answer("На этот день свободного времени нет 😔", show_alert=True)
        return
    await state.update_data(day=callback_data.day)
    await state.set_state(Booking.time)
    await call.message.edit_text(f"{kb.day_label(day)} — выбери время:", reply_markup=kb.times_kb(slots))
    await call.answer()


# ---------- кнопки «назад» ----------
@router.callback_query(kb.BackCb.filter(F.to == "services"))
async def back_to_services(call: CallbackQuery, state: FSMContext, db: Database):
    await state.set_state(Booking.service)
    await call.message.edit_text("Выбери услугу:", reply_markup=kb.services_kb(await db.services()))
    await call.answer()


@router.callback_query(kb.BackCb.filter(F.to == "days"))
async def back_to_days(call: CallbackQuery, state: FSMContext, settings: Settings):
    await state.set_state(Booking.day)
    days = booking_days(now_local(settings).date(), settings.days_ahead)
    await call.message.edit_text("Выбери день:", reply_markup=kb.days_kb(days))
    await call.answer()


# ---------- шаг 3: время ----------
@router.callback_query(Booking.time, kb.TimeCb.filter())
async def pick_time(call: CallbackQuery, callback_data: kb.TimeCb, state: FSMContext):
    data = await state.get_data()
    hhmm = callback_data.hhmm
    start_at = f"{data['day']} {hhmm[:2]}:{hhmm[2:]}"
    await state.update_data(start_at=start_at)
    await state.set_state(Booking.phone)
    await call.message.edit_text(f"Время: <b>{start_at[11:]}</b>")
    await call.message.answer(
        "Отправь номер телефона кнопкой ниже или напиши его сообщением:",
        reply_markup=kb.phone_kb(),
    )
    await call.answer()


# ---------- шаг 4: телефон ----------
@router.message(Booking.phone, F.contact)
async def got_contact(message: Message, state: FSMContext, db: Database):
    await ask_confirm(message, state, db, message.contact.phone_number)


@router.message(Booking.phone, F.text)
async def got_phone_text(message: Message, state: FSMContext, db: Database):
    if not PHONE_RE.match(message.text.strip()):
        await message.answer("Не похоже на номер. Пример: +7 999 123-45-67")
        return
    await ask_confirm(message, state, db, message.text.strip())


async def ask_confirm(message: Message, state: FSMContext, db: Database, phone: str):
    await state.update_data(phone=phone)
    await state.set_state(Booking.confirm)
    data = await state.get_data()
    service = await db.service(data["service_id"])
    dt = datetime.strptime(data["start_at"], FMT)
    await message.answer("Проверь запись 👇", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        f"Услуга: <b>{service['name']}</b> ({service['price']} ₽)\n"
        f"Когда: <b>{kb.day_label(dt.date())}, {dt:%H:%M}</b>\n"
        f"Телефон: {phone}",
        reply_markup=kb.confirm_kb(),
    )


# ---------- шаг 5: подтверждение ----------
@router.callback_query(Booking.confirm, kb.ConfirmCb.filter())
async def confirm(call: CallbackQuery, callback_data: kb.ConfirmCb, state: FSMContext,
                  db: Database, settings: Settings, bot: Bot):
    data = await state.get_data()
    await state.clear()

    if not callback_data.yes:
        await call.message.edit_text("Запись отменена.")
        await call.message.answer("Главное меню", reply_markup=kb.main_menu())
        await call.answer()
        return

    # Время могло пройти, пока человек вводил телефон
    if datetime.strptime(data["start_at"], FMT) <= now_local(settings):
        await call.message.edit_text("Это время уже прошло. Попробуй выбрать другое.")
        await call.message.answer("Главное меню", reply_markup=kb.main_menu())
        await call.answer()
        return

    try:
        booking_id = await db.create_booking(
            call.from_user.id, call.from_user.full_name, data["phone"],
            data["service_id"], data["start_at"],
        )
    except SlotTaken:
        await call.message.edit_text("Ой, это время только что заняли 😔 Выбери другое.")
        await call.message.answer("Главное меню", reply_markup=kb.main_menu())
        await call.answer()
        return

    b = await db.get_booking(booking_id)
    await call.message.edit_text(
        f"✅ Готово! Ждём тебя {b.start_at[8:10]}.{b.start_at[5:7]} в {b.start_at[11:]}.\n"
        "Напомню заранее. Отменить можно в «Мои записи»."
    )
    await call.message.answer("Главное меню", reply_markup=kb.main_menu())
    await call.answer()
    await notify_admins(bot, settings,
                        f"🆕 Новая запись\n{b.start_at} — {b.service}\n{b.user_name}, {b.phone}")


# ---------- мои записи и отмена ----------
@router.message(F.text == kb.BTN_MY)
async def my_bookings(message: Message, db: Database, settings: Settings):
    now = now_local(settings).strftime(FMT)
    bookings = await db.user_bookings(message.from_user.id, now)
    if not bookings:
        await message.answer("У тебя нет активных записей.")
        return
    lines = [f"• {b.start_at[8:10]}.{b.start_at[5:7]} {b.start_at[11:]} — {b.service}" for b in bookings]
    await message.answer("Твои записи:\n" + "\n".join(lines), reply_markup=kb.my_bookings_kb(bookings))


@router.callback_query(kb.CancelCb.filter())
async def cancel_my(call: CallbackQuery, callback_data: kb.CancelCb, db: Database,
                    settings: Settings, bot: Bot):
    b = await db.get_booking(callback_data.id)
    # user_id в запросе не даёт отменить чужую запись подделанной кнопкой
    if not b or not await db.cancel_booking(callback_data.id, user_id=call.from_user.id):
        await call.answer("Запись уже отменена или не найдена", show_alert=True)
        return
    await call.message.edit_text(f"Запись на {b.start_at} отменена.")
    await call.answer()
    await notify_admins(bot, settings, f"❌ Клиент отменил запись\n{b.start_at} — {b.service}\n{b.user_name}, {b.phone}")


async def notify_admins(bot: Bot, settings: Settings, text: str):
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:  # админ мог не нажать /start или заблокировать бота
            log.warning("Не удалось уведомить админа %s: %s", admin_id, e)
