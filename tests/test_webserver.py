import unittest
from datetime import date, timedelta

from tasklistprogram import webserver as ws


def fresh_db():
    return {"version": 1, "tasks": [], "next_id": 1}


class AdapterTests(unittest.TestCase):
    def test_to_client_maps_done_and_times(self):
        c = ws.to_client({"id": 1, "title": "x", "completed_at": "2026-01-01T00:00:00",
                          "times_completed": 5, "priority": "H"})
        self.assertTrue(c["done"])
        self.assertEqual(c["times"], 5)
        self.assertEqual(c["priority"], "H")

    def test_client_tasks_includes_deleted_with_flag(self):
        # The client now receives ALL tasks (incl. deleted) so it can show a
        # Deleted view / restore — deletion is conveyed via the is_deleted flag.
        db = {"tasks": [{"id": 1, "is_deleted": True}, {"id": 2}]}
        out = ws.client_tasks(db)
        self.assertEqual([t["id"] for t in out], [1, 2])
        self.assertEqual([t["is_deleted"] for t in out], [True, False])


class HazardResetTests(unittest.TestCase):
    def test_reset_clears_skip_and_restores_base_priority(self):
        db = {"tasks": [
            {"id": 1, "skip_count": 3, "priority": "U", "base_priority": "M"},
            {"id": 2, "skip_count": 0, "priority": "L"},
        ]}
        count = ws.op_reset_hazard(db)
        self.assertGreaterEqual(count, 1)
        self.assertEqual(db["tasks"][0]["skip_count"], 0)
        self.assertEqual(db["tasks"][0]["priority"], "M")
        self.assertNotIn("base_priority", db["tasks"][0])


class OpAddTests(unittest.TestCase):
    def test_add_basic(self):
        db = fresh_db()
        t = ws.op_add(db, {"title": "Write report", "priority": "H"})
        self.assertEqual(t["title"], "Write report")
        self.assertEqual(t["priority"], "H")
        self.assertEqual(db["next_id"], 2)

    def test_add_requires_title(self):
        with self.assertRaises(ValueError):
            ws.op_add(fresh_db(), {"title": "   "})

    def test_add_misc_maps_to_x_and_daily_for_d(self):
        db = fresh_db()
        self.assertEqual(ws.op_add(db, {"title": "a", "priority": "Misc"})["priority"], "X")
        d = ws.op_add(db, {"title": "b", "priority": "D"})
        self.assertEqual(d["repeat"], "daily")

    def test_add_parses_due(self):
        t = ws.op_add(fresh_db(), {"title": "a", "due": "tomorrow"})
        self.assertEqual(t["due"], (date.today() + timedelta(days=1)).strftime("%Y-%m-%d"))

    def test_add_rejects_invalid_due_with_import_wording(self):
        db = fresh_db()
        with self.assertRaises(ValueError) as cm:
            ws.op_add(db, {"title": "a", "due": "notadate"})
        self.assertTrue(str(cm.exception).startswith("invalid due 'notadate'. Use "))
        self.assertEqual(db["tasks"], [])

    def test_add_rejects_invalid_repeat(self):
        with self.assertRaises(ValueError) as cm:
            ws.op_add(fresh_db(), {"title": "a", "repeat": "fortnightly"})
        self.assertTrue(str(cm.exception).startswith("invalid repeat 'fortnightly'. Use "))
        with self.assertRaises(ValueError):
            ws.op_add(fresh_db(), {"title": "a", "repeat": "custom:0"})

    def test_add_normalizes_custom_repeat_and_tolerates_non_strings(self):
        t = ws.op_add(fresh_db(), {"title": "a", "repeat": "Custom: 06"})
        self.assertEqual(t["repeat"], "custom:6")
        t = ws.op_add(fresh_db(), {"title": 42, "notes": None, "group": 7})
        self.assertEqual((t["title"], t["notes"], t["group"]), ("42", "", "7"))


class OpUpdateTests(unittest.TestCase):
    def base(self):
        return {"id": 1, "title": "a", "due": "2026-01-01", "priority": "M", "repeat": "none",
                "group": "", "notes": "", "completed_at": "", "times_completed": 0, "history": [],
                "is_suspended": False, "is_deleted": False}

    def test_update_basic_fields(self):
        t = self.base()
        ws.op_update(t, {"title": "b", "notes": "n", "group": "G", "priority": "H", "repeat": "weekly"})
        self.assertEqual((t["title"], t["notes"], t["group"], t["priority"], t["repeat"]), ("b", "n", "G", "H", "weekly"))

    def test_update_misc_and_daily(self):
        t = self.base()
        ws.op_update(t, {"priority": "Misc"})
        self.assertEqual(t["priority"], "X")
        ws.op_update(t, {"priority": "D"})
        self.assertEqual((t["priority"], t["repeat"]), ("D", "daily"))

    def test_update_due_parsed_and_cleared(self):
        t = self.base()
        ws.op_update(t, {"due": "tomorrow"})
        from datetime import date, timedelta
        self.assertEqual(t["due"], (date.today() + timedelta(days=1)).strftime("%Y-%m-%d"))
        ws.op_update(t, {"due": ""})
        self.assertEqual(t["due"], "")

    def test_update_suspend_and_delete_flags(self):
        t = self.base()
        ws.op_update(t, {"is_suspended": True})
        self.assertTrue(t["is_suspended"])
        ws.op_update(t, {"is_deleted": True})
        self.assertTrue(t["is_deleted"])

    def test_update_restore_snapshot_for_undo(self):
        t = self.base()
        t.update({"due": "2026-02-02", "completed_at": "x", "times_completed": 9, "history": ["2026-01-01"]})
        ws.op_update(t, {"due": "2026-01-01", "completed_at": "", "times": 8, "history": []})
        self.assertEqual(t["due"], "2026-01-01")
        self.assertEqual(t["completed_at"], "")
        self.assertEqual(t["times_completed"], 8)
        self.assertEqual(t["history"], [])

    def test_update_ignores_blank_title(self):
        t = self.base()
        ws.op_update(t, {"title": "   "})
        self.assertEqual(t["title"], "a")

    def test_update_rejects_invalid_due_and_changes_nothing(self):
        t = self.base()
        with self.assertRaises(ValueError) as cm:
            ws.op_update(t, {"title": "changed", "due": "notadate"})
        self.assertIn("invalid due 'notadate'", str(cm.exception))
        self.assertEqual((t["title"], t["due"]), ("a", "2026-01-01"))
        self.assertNotIn("updated_at", t)

    def test_update_rejects_invalid_repeat(self):
        t = self.base()
        with self.assertRaises(ValueError):
            ws.op_update(t, {"repeat": "fortnightly"})
        self.assertEqual(t["repeat"], "none")
        ws.op_update(t, {"repeat": "custom:6"})
        self.assertEqual(t["repeat"], "custom:6")


class OpDoneTests(unittest.TestCase):
    def test_mark_done_oneoff(self):
        t = {"id": 1, "title": "a", "repeat": "none", "due": "", "completed_at": "", "times_completed": 0}
        ws.op_mark_done(t)
        self.assertTrue(t["completed_at"])
        self.assertEqual(t["times_completed"], 1)
        self.assertEqual(len(t["history"]), 1)

    def test_mark_done_recurring_advances_and_stays_active(self):
        today = date.today().strftime("%Y-%m-%d")
        t = {"id": 1, "title": "a", "repeat": "daily", "due": today, "completed_at": "", "times_completed": 0}
        ws.op_mark_done(t)
        self.assertEqual(t["completed_at"], "")  # resets for next cycle
        self.assertEqual(t["due"], (date.today() + timedelta(days=1)).strftime("%Y-%m-%d"))
        self.assertEqual(t["times_completed"], 1)

    def test_mark_done_overdue_recurring_lands_on_next_future_occurrence(self):
        # Due three days ago: one completion should jump past today, not to two days ago.
        old = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d")
        t = {"id": 1, "title": "a", "repeat": "daily", "due": old, "completed_at": "", "times_completed": 0}
        ws.op_mark_done(t)
        self.assertEqual(t["due"], (date.today() + timedelta(days=1)).strftime("%Y-%m-%d"))
        self.assertEqual(len(t["history"]), 1)

    def test_mark_done_keeps_time_of_day_when_catching_up(self):
        old = (date.today() - timedelta(days=2)).strftime("%Y-%m-%d") + " 09:30"
        t = {"id": 1, "title": "a", "repeat": "daily", "due": old, "completed_at": "", "times_completed": 0}
        ws.op_mark_done(t)
        self.assertEqual(t["due"], (date.today() + timedelta(days=1)).strftime("%Y-%m-%d") + " 09:30")

    def test_mark_done_unknown_repeat_keeps_due(self):
        t = {"id": 1, "title": "a", "repeat": "fortnightly", "due": "2026-01-01", "completed_at": "", "times_completed": 0}
        ws.op_mark_done(t)
        self.assertEqual(t["due"], "2026-01-01")

    def test_toggle_undo(self):
        t = {"id": 1, "repeat": "none", "due": "", "completed_at": "x"}
        ws.op_toggle(t)
        self.assertEqual(t["completed_at"], "")

    def test_toggle_marks_done_when_open(self):
        t = {"id": 1, "repeat": "none", "due": "", "completed_at": "", "times_completed": 0}
        ws.op_toggle(t)
        self.assertTrue(t["completed_at"])


if __name__ == "__main__":
    unittest.main()
