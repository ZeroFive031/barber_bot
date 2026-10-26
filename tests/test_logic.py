"""Тесты логики без Telegram. Запуск из папки проекта: python -m unittest -v"""
import asyncio
import os
import sys
import tempfile
import unittest
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import Database, SlotTaken  # noqa: E402
from slots import booking_days, day_slots, free_slots  # noqa: E402


class SlotsTest(unittest.TestCase):
    def test_day_slots(self):
        s = day_slots(date(2026, 10, 27), 10, 20, 60)
        self.assertEqual(len(s), 10)
        self.assertEqual(f"{s[0]:%H:%M}", "10:00")
        self.assertEqual(f"{s[-1]:%H:%M}", "19:00")

    def test_slot_must_fit_before_close(self):
        s = day_slots(date(2026, 10, 27), 10, 20, 90)
        self.assertEqual(f"{s[-1]:%H:%M}", "17:30")  # 19:00 + 1.5ч уже после 20:00

    def test_free_slots_excludes_busy_and_past(self):
        day = date(2026, 10, 27)
        now = datetime(2026, 10, 27, 12, 30)
        free = free_slots(day, {"2026-10-27 14:00"}, now, 10, 20, 60)
        hours = [s.hour for s in free]
        self.assertEqual(hours, [13, 15, 16, 17, 18, 19])

    def test_booking_days(self):
        days = booking_days(date(2026, 10, 30), 3)
        self.assertEqual([d.isoformat() for d in days], ["2026-10-30", "2026-10-31", "2026-11-01"])


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "t.db"))
        asyncio.run(self.db.init())

    def tearDown(self):
        self.tmp.cleanup()

    def run_(self, coro):
        return asyncio.run(coro)

    def test_default_services(self):
        self.assertEqual(len(self.run_(self.db.services())), 3)

    def test_double_booking_blocked(self):
        self.run_(self.db.create_booking(1, "A", "+7999", 1, "2026-10-27 14:00"))
        with self.assertRaises(SlotTaken):
            self.run_(self.db.create_booking(2, "B", "+7888", 2, "2026-10-27 14:00"))

    def test_concurrent_booking_only_one_wins(self):
        async def race():
            async def attempt(uid):
                try:
                    await self.db.create_booking(uid, "U", "+7", 1, "2026-10-27 15:00")
                    return True
                except SlotTaken:
                    return False
            return await asyncio.gather(*(attempt(i) for i in range(10)))
        results = self.run_(race())
        self.assertEqual(sum(results), 1)

    def test_cancel_frees_slot_and_protects_others(self):
        bid = self.run_(self.db.create_booking(1, "A", "+7", 1, "2026-10-27 16:00"))
        # чужой пользователь не может отменить
        self.assertFalse(self.run_(self.db.cancel_booking(bid, user_id=999)))
        self.assertTrue(self.run_(self.db.cancel_booking(bid, user_id=1)))
        self.assertEqual(self.run_(self.db.busy_times("2026-10-27")), set())
        # после отмены время снова можно занять
        self.run_(self.db.create_booking(2, "B", "+7", 1, "2026-10-27 16:00"))

    def test_user_and_day_bookings(self):
        self.run_(self.db.create_booking(1, "A", "+7", 1, "2026-10-27 10:00"))
        self.run_(self.db.create_booking(1, "A", "+7", 2, "2026-10-28 11:00"))
        self.run_(self.db.create_booking(2, "B", "+7", 3, "2026-10-27 12:00"))
        mine = self.run_(self.db.user_bookings(1, "2026-10-27 11:00"))
        self.assertEqual([b.start_at for b in mine], ["2026-10-28 11:00"])
        day = self.run_(self.db.day_bookings("2026-10-27"))
        self.assertEqual([b.user_name for b in day], ["A", "B"])
        self.assertEqual(day[1].service, "Стрижка + борода")

    def test_reminders_sent_once(self):
        bid = self.run_(self.db.create_booking(1, "A", "+7", 1, "2026-10-27 14:00"))
        self.run_(self.db.create_booking(2, "B", "+7", 1, "2026-10-27 18:00"))
        due = self.run_(self.db.due_reminders("2026-10-27 12:30", "2026-10-27 14:30"))
        self.assertEqual([b.id for b in due], [bid])
        self.run_(self.db.mark_reminded(bid))
        self.assertEqual(self.run_(self.db.due_reminders("2026-10-27 12:31", "2026-10-27 14:31")), [])


if __name__ == "__main__":
    unittest.main()
