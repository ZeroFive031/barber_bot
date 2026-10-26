"""Работа с базой SQLite.

Используем стандартный sqlite3 и выносим запросы в отдельный поток через
asyncio.to_thread, чтобы не блокировать бота. Для маленького бота этого хватает;
при росте нагрузки базу меняют на PostgreSQL (asyncpg).
"""
import asyncio
import sqlite3
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS services (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    price     INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS bookings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    user_name  TEXT,
    phone      TEXT NOT NULL,
    service_id INTEGER NOT NULL REFERENCES services(id),
    start_at   TEXT NOT NULL,              -- 'YYYY-MM-DD HH:MM'
    status     TEXT NOT NULL DEFAULT 'active',  -- active / cancelled
    reminded   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Главная защита от двойной записи: на одно время может быть только одна
-- активная запись. Даже если два человека нажмут кнопку одновременно,
-- база пропустит только одного.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_slot
    ON bookings(start_at) WHERE status = 'active';
"""

DEFAULT_SERVICES = [
    ("Мужская стрижка", 1500),
    ("Стрижка бороды", 800),
    ("Стрижка + борода", 2000),
]


class SlotTaken(Exception):
    """Время уже занято кем-то другим."""


@dataclass
class Booking:
    id: int
    user_id: int
    user_name: str | None
    phone: str
    service: str
    price: int
    start_at: str


class Database:
    def __init__(self, path: str):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _run(self, fn):
        # Своё соединение на каждую операцию: просто и безопасно для потоков.
        def wrapper():
            conn = self._connect()
            try:
                with conn:  # автоматически commit / rollback
                    return fn(conn)
            finally:
                conn.close()
        return asyncio.to_thread(wrapper)

    # ---------- инициализация ----------
    async def init(self) -> None:
        def fn(c):
            c.executescript(SCHEMA)
            if c.execute("SELECT COUNT(*) FROM services").fetchone()[0] == 0:
                c.executemany("INSERT INTO services(name, price) VALUES (?, ?)", DEFAULT_SERVICES)
        await self._run(fn)

    # ---------- услуги ----------
    async def services(self) -> list[sqlite3.Row]:
        return await self._run(
            lambda c: c.execute("SELECT * FROM services WHERE is_active = 1 ORDER BY id").fetchall()
        )

    async def service(self, service_id: int) -> sqlite3.Row | None:
        return await self._run(
            lambda c: c.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()
        )

    # ---------- записи ----------
    async def busy_times(self, day: str) -> set[str]:
        """Занятые времена на день 'YYYY-MM-DD'."""
        rows = await self._run(lambda c: c.execute(
            "SELECT start_at FROM bookings WHERE status = 'active' AND start_at LIKE ?",
            (f"{day}%",),
        ).fetchall())
        return {r["start_at"] for r in rows}

    async def create_booking(self, user_id, user_name, phone, service_id, start_at) -> int:
        def fn(c):
            try:
                cur = c.execute(
                    "INSERT INTO bookings(user_id, user_name, phone, service_id, start_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user_id, user_name, phone, service_id, start_at),
                )
                return cur.lastrowid
            except sqlite3.IntegrityError:
                raise SlotTaken(start_at)
        return await self._run(fn)

    _SELECT = (
        "SELECT b.id, b.user_id, b.user_name, b.phone, s.name AS service, s.price, b.start_at "
        "FROM bookings b JOIN services s ON s.id = b.service_id "
    )

    async def user_bookings(self, user_id: int, now: str) -> list[Booking]:
        rows = await self._run(lambda c: c.execute(
            self._SELECT + "WHERE b.user_id = ? AND b.status = 'active' AND b.start_at >= ? "
            "ORDER BY b.start_at",
            (user_id, now),
        ).fetchall())
        return [Booking(**dict(r)) for r in rows]

    async def day_bookings(self, day: str) -> list[Booking]:
        rows = await self._run(lambda c: c.execute(
            self._SELECT + "WHERE b.status = 'active' AND b.start_at LIKE ? ORDER BY b.start_at",
            (f"{day}%",),
        ).fetchall())
        return [Booking(**dict(r)) for r in rows]

    async def get_booking(self, booking_id: int) -> Booking | None:
        row = await self._run(lambda c: c.execute(
            self._SELECT + "WHERE b.id = ? AND b.status = 'active'", (booking_id,)
        ).fetchone())
        return Booking(**dict(row)) if row else None

    async def cancel_booking(self, booking_id: int, user_id: int | None = None) -> bool:
        """Отменить запись. Если передан user_id — только свою (защита от чужих отмен)."""
        def fn(c):
            sql = "UPDATE bookings SET status = 'cancelled' WHERE id = ? AND status = 'active'"
            args: list = [booking_id]
            if user_id is not None:
                sql += " AND user_id = ?"
                args.append(user_id)
            return c.execute(sql, args).rowcount > 0
        return await self._run(fn)

    # ---------- напоминания ----------
    async def due_reminders(self, now: str, until: str) -> list[Booking]:
        rows = await self._run(lambda c: c.execute(
            self._SELECT + "WHERE b.status = 'active' AND b.reminded = 0 "
            "AND b.start_at > ? AND b.start_at <= ?",
            (now, until),
        ).fetchall())
        return [Booking(**dict(r)) for r in rows]

    async def mark_reminded(self, booking_id: int) -> None:
        await self._run(lambda c: c.execute(
            "UPDATE bookings SET reminded = 1 WHERE id = ?", (booking_id,)
        ))
