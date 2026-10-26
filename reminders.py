"""Фоновая задача: раз в минуту ищет записи, до которых осталось мало времени, и напоминает."""
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot

from config import Settings
from db import Database
from slots import FMT

log = logging.getLogger(__name__)


async def reminder_loop(bot: Bot, db: Database, settings: Settings, interval: int = 60):
    while True:
        try:
            now = datetime.now(settings.tz).replace(tzinfo=None)
            until = now + timedelta(minutes=settings.remind_before_min)
            for b in await db.due_reminders(now.strftime(FMT), until.strftime(FMT)):
                try:
                    await bot.send_message(
                        b.user_id,
                        f"⏰ Напоминание: сегодня в {b.start_at[11:]} у вас {b.service.lower()}. Ждём!",
                    )
                except Exception as e:
                    log.warning("Напоминание %s не отправлено: %s", b.id, e)
                # Помечаем в любом случае, чтобы не спамить каждую минуту
                await db.mark_reminded(b.id)
        except Exception:
            # Ошибка в одной итерации не должна убить цикл навсегда
            log.exception("Ошибка в цикле напоминаний")
        await asyncio.sleep(interval)
