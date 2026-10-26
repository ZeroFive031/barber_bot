"""Расчёт свободного времени. Чистые функции без Telegram — их легко тестировать."""
from datetime import date, datetime, timedelta

FMT = "%Y-%m-%d %H:%M"  # так время хранится в базе (локальное время салона)


def day_slots(day: date, work_start: int, work_end: int, slot_minutes: int) -> list[datetime]:
    """Все слоты рабочего дня: 10:00, 11:00, ... пока запись помещается до конца дня."""
    start = datetime(day.year, day.month, day.day, work_start)
    end = datetime(day.year, day.month, day.day, work_end)
    step = timedelta(minutes=slot_minutes)
    slots, t = [], start
    while t + step <= end:
        slots.append(t)
        t += step
    return slots


def free_slots(
    day: date,
    busy: set[str],
    now: datetime,
    work_start: int,
    work_end: int,
    slot_minutes: int,
) -> list[datetime]:
    """Слоты дня минус занятые и минус уже прошедшие (now — локальное время без tzinfo)."""
    return [
        s for s in day_slots(day, work_start, work_end, slot_minutes)
        if s.strftime(FMT) not in busy and s > now
    ]


def booking_days(today: date, days_ahead: int) -> list[date]:
    return [today + timedelta(days=i) for i in range(days_ahead)]
