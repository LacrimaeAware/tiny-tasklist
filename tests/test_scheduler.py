import unittest
from datetime import date, timedelta

from tasklistprogram.core import scheduler


def task(**kw):
    base = {"id": 1, "title": "t", "priority": "M", "due": "", "repeat": "daily",
            "completed_at": "", "skip_count": 0}
    base.update(kw)
    return base


class AdvanceRepeatingTests(unittest.TestCase):
    def test_advances_past_today(self):
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        db = {"tasks": [task(due=yesterday, repeat="daily")]}
        changed = scheduler.advance_repeating_tasks(db, today=date.today())
        self.assertTrue(changed)
        self.assertEqual(db["tasks"][0]["due"], date.today().strftime("%Y-%m-%d"))

    def test_no_change_when_future(self):
        future = (date.today() + timedelta(days=3)).strftime("%Y-%m-%d")
        db = {"tasks": [task(due=future, repeat="daily")]}
        self.assertFalse(scheduler.advance_repeating_tasks(db, today=date.today()))
        self.assertEqual(db["tasks"][0]["due"], future)

    def test_catches_up_multiple_missed(self):
        old = (date.today() - timedelta(days=10)).strftime("%Y-%m-%d")
        db = {"tasks": [task(due=old, repeat="daily")]}
        scheduler.advance_repeating_tasks(db, today=date.today())
        self.assertEqual(db["tasks"][0]["due"], date.today().strftime("%Y-%m-%d"))

    def test_preserves_time_of_day(self):
        old = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d") + " 09:30"
        db = {"tasks": [task(due=old, repeat="daily")]}
        scheduler.advance_repeating_tasks(db, today=date.today())
        self.assertTrue(db["tasks"][0]["due"].endswith("09:30"))

    def test_reactivates_completed_due_today(self):
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        db = {"tasks": [task(due=yesterday, repeat="daily", completed_at="2026-01-01T00:00:00")]}
        scheduler.advance_repeating_tasks(db, today=date.today())
        self.assertEqual(db["tasks"][0]["completed_at"], "")

    def test_ignores_non_repeating(self):
        old = (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")
        db = {"tasks": [task(due=old, repeat="none")]}
        self.assertFalse(scheduler.advance_repeating_tasks(db, today=date.today()))
        self.assertEqual(db["tasks"][0]["due"], old)

    def test_malformed_repeat_does_not_hang(self):
        old = (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")
        db = {"tasks": [task(due=old, repeat="custom:0")]}
        # Should return promptly (no infinite loop) thanks to the no-progress guard.
        scheduler.advance_repeating_tasks(db, today=date.today())


class HazardEscalationTests(unittest.TestCase):
    def test_escalation_on_missed(self):
        old = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d")
        t = task(due=old, repeat="daily", priority="M", skip_count=0)
        db = {"tasks": [t]}
        scheduler.advance_repeating_tasks(db, today=date.today(), hazard_enabled=True)
        self.assertGreaterEqual(t["skip_count"], 3)
        self.assertEqual(t["priority"], "U")
        self.assertEqual(t["base_priority"], "M")

    def test_no_escalation_when_disabled(self):
        old = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d")
        t = task(due=old, repeat="daily", priority="M", skip_count=0)
        scheduler.advance_repeating_tasks({"tasks": [t]}, today=date.today(), hazard_enabled=False)
        self.assertEqual(t["skip_count"], 0)
        self.assertEqual(t["priority"], "M")

    def test_apply_skip_escalation_steps(self):
        t = {"priority": "L", "skip_count": 0}
        scheduler.apply_skip_escalation(t)
        self.assertEqual(t["skip_count"], 1)
        scheduler.apply_skip_escalation(t)
        self.assertEqual(t["priority"], "H")
        self.assertEqual(t["base_priority"], "L")
        scheduler.apply_skip_escalation(t)
        self.assertEqual(t["priority"], "U")


if __name__ == "__main__":
    unittest.main()
