import unittest
from datetime import datetime, timedelta

from tasklistprogram.core import reminders


def make_task(priority="H", created_days_ago=10, due_days_ahead=10, **kw):
    now = datetime.now()
    t = {
        "id": 1,
        "title": "t",
        "priority": priority,
        "created_at": (now - timedelta(days=created_days_ago)).isoformat(timespec="seconds"),
        "due": (now + timedelta(days=due_days_ahead)).strftime("%Y-%m-%d %H:%M"),
        "is_deleted": False,
        "completed_at": "",
        "acknowledged_checkpoints": [],
    }
    t.update(kw)
    return t


ENABLED = {"reminders_enabled": True, "reminder_count": 4, "reminder_min_priority": "M"}


class ReminderChipTests(unittest.TestCase):
    def test_chip_for_high_priority_with_elapsed_checkpoint(self):
        self.assertEqual(reminders.reminder_chip(make_task(priority="H"), ENABLED), "⏰")

    def test_ultra_priority_gets_chip(self):
        # Regression: Ultra used to be ranked as lowest and silently skipped.
        self.assertEqual(reminders.reminder_chip(make_task(priority="U"), ENABLED), "⏰")

    def test_misc_priority_below_threshold(self):
        self.assertEqual(reminders.reminder_chip(make_task(priority="X"), ENABLED), "")

    def test_low_priority_below_threshold(self):
        self.assertEqual(reminders.reminder_chip(make_task(priority="L"), ENABLED), "")

    def test_disabled_returns_empty(self):
        disabled = dict(ENABLED, reminders_enabled=False)
        self.assertEqual(reminders.reminder_chip(make_task(priority="H"), disabled), "")

    def test_no_due_returns_empty(self):
        self.assertEqual(reminders.reminder_chip(make_task(priority="H", due=""), ENABLED), "")

    def test_acknowledged_checkpoints_suppress_chip(self):
        # pending_reminders surfaces one (latest) checkpoint at a time, so clearing
        # the chip can require acknowledging successively until none remain.
        t = make_task(priority="H")
        db = {"tasks": [t], "settings": ENABLED}
        for _ in range(20):
            rows = reminders.pending_reminders(db)
            if not rows:
                break
            acks = set(t.get("acknowledged_checkpoints", []))
            acks.update(r["_cp_key"] for r in rows)
            t["acknowledged_checkpoints"] = sorted(acks)
        self.assertEqual(reminders.reminder_chip(t, ENABLED), "")


class PendingRemindersTests(unittest.TestCase):
    def test_pending_includes_high_priority(self):
        rows = reminders.pending_reminders({"tasks": [make_task(priority="H")], "settings": ENABLED})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], 1)

    def test_pending_excludes_completed(self):
        t = make_task(priority="H", completed_at="2026-01-01T00:00:00")
        self.assertEqual(reminders.pending_reminders({"tasks": [t], "settings": ENABLED}), [])

    def test_pending_empty_when_disabled(self):
        settings = dict(ENABLED, reminders_enabled=False)
        self.assertEqual(reminders.pending_reminders({"tasks": [make_task()], "settings": settings}), [])


if __name__ == "__main__":
    unittest.main()
