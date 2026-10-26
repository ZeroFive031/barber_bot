"""Точка входа: python bot.py"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import load_settings
from db import Database
from handlers import admin, client
from reminders import reminder_loop


async def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    db = Database(settings.db_path)
    await db.init()

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    # Всё, что положено в dp, aiogram передаёт в хендлеры по имени аргумента
    dp["db"] = db
    dp["settings"] = settings

    # Админский роутер первым: его команды не должны перехватываться клиентскими
    dp.include_router(admin.router)
    dp.include_router(client.router)

    reminders = asyncio.create_task(reminder_loop(bot, db, settings))
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        reminders.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
