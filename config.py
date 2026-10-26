"""Настройки бота. Всё берётся из файла .env (см. .env.example)."""
import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _ids(raw: str) -> set[int]:
    return {int(x) for x in raw.replace(" ", "").split(",") if x}


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: set[int]
    tz: ZoneInfo
    work_start: int      # час начала работы, например 10
    work_end: int        # час окончания, например 20 (последний слот начинается раньше)
    slot_minutes: int    # длительность одной записи
    days_ahead: int      # на сколько дней вперёд можно записаться
    remind_before_min: int
    db_path: str


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        raise RuntimeError("Не задан BOT_TOKEN в .env")
    return Settings(
        bot_token=token,
        admin_ids=_ids(os.getenv("ADMIN_IDS", "")),
        tz=ZoneInfo(os.getenv("TZ_NAME", "Europe/Moscow")),
        work_start=int(os.getenv("WORK_START", "10")),
        work_end=int(os.getenv("WORK_END", "20")),
        slot_minutes=int(os.getenv("SLOT_MINUTES", "60")),
        days_ahead=int(os.getenv("DAYS_AHEAD", "7")),
        remind_before_min=int(os.getenv("REMIND_BEFORE_MIN", "120")),
        db_path=os.getenv("DB_PATH", "bot.db"),
    )
