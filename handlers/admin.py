"""Панель мастера: просмотр записей по дням и отмена с уведомлением клиента."""
import logging
from datetime import datetime

from aiogram import Bot, Router
from aiogram.filters import Command, Filter
from aiogram.types import CallbackQuery, Message, TelegramObject

import keyboards as kb
from config import Settings
from db import Database
from slots import booking_days

router = Router()
log = logging.getLogger(__name__)


class IsAdmin(Filter):
    # settings aiogram подставит сам из данных диспетчера (dp["settings"])
    async def __call__(self, event: TelegramObject, settings: Settings) -> bool:
        return event.from_user is not None and event.from_user.id in settings.admin_ids


# Фильтр на весь роутер: все хендлеры ниже работают только для админов
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(Command("admin"))
async def admin_menu(message: Message, settings: Settings):
    today = datetime.now(settings.tz).date()
    await message.answer("Панель мастера. Выбери день:",
                         reply_markup=kb.admin_days_kb(booking_days(today, settings.days_ahead)))


async def render_day(day: str, db: Database):
    bookings = await db.day_bookings(day)
    if not bookings:
        return f"{day}: записей нет.", None
    lines = [f"{b.start_at[11:]} — {b.service} — {b.user_name}, {b.phone}" for b in bookings]
    text = f"<b>Записи на {day}</b>\n" + "\n".join(lines) + "\n\nНажми на запись, чтобы отменить её."
    return text, kb.admin_bookings_kb(bookings)


@router.callback_query(kb.AdminDayCb.filter())
async def admin_day(call: CallbackQuery, callback_data: kb.AdminDayCb, db: Database):
    text, markup = await render_day(callback_data.day, db)
    await call.message.edit_text(text, reply_markup=markup)
    await call.answer()


@router.callback_query(kb.AdminCancelCb.filter())
async def admin_cancel(call: CallbackQuery, callback_data: kb.AdminCancelCb, db: Database, bot: Bot):
    b = await db.get_booking(callback_data.id)
    if not b or not await db.cancel_booking(b.id):
        await call.answer("Уже отменена", show_alert=True)
        return
    try:
        await bot.send_message(
            b.user_id,
            f"😔 К сожалению, мастер отменил вашу запись на {b.start_at}.\n"
            "Выберите другое время через «📅 Записаться».",
        )
    except Exception as e:
        log.warning("Не удалось уведомить клиента %s: %s", b.user_id, e)
    text, markup = await render_day(b.start_at[:10], db)
    await call.message.edit_text(text, reply_markup=markup)
    await call.answer("Запись отменена, клиент уведомлён")
