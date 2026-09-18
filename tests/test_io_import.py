import unittest

from tasklistprogram.core.io_import import import_from_string


def fresh_db():
    return {"version": 1, "tasks": [], "next_id": 1}


class ImportTests(unittest.TestCase):
    def test_title_only(self):
        db = fresh_db()
        added, failed = import_from_string("Buy groceries", db)
        self.assertEqual((added, failed), (1, 0))
        self.assertEqual(db["tasks"][0]["title"], "Buy groceries")
        self.assertEqual(db["next_id"], 2)

    def test_full_fields(self):
        db = fresh_db()
        import_from_string("Exam | due: 2026-10-13 14:00 | prio: H | group: School | notes: bring pen", db)
        t = db["tasks"][0]
        self.assertEqual(t["priority"], "H")
        self.assertEqual(t["due"], "2026-10-13 14:00")
        self.assertEqual(t["group"], "School")
        self.assertEqual(t["notes"], "bring pen")

    def test_prio_d_forces_daily(self):
        db = fresh_db()
        import_from_string("Standup | prio: D", db)
        self.assertEqual(db["tasks"][0]["repeat"], "daily")

    def test_misc_maps_to_x(self):
        db = fresh_db()
        import_from_string("Someday | prio: Misc", db)
        self.assertEqual(db["tasks"][0]["priority"], "X")

    def test_custom_repeat(self):
        db = fresh_db()
        import_from_string("Water plants | repeat: custom:6", db)
        self.assertEqual(db["tasks"][0]["repeat"], "custom:6")

    def test_bare_time_due(self):
        db = fresh_db()
        import_from_string("Call | due: 0830", db)
        self.assertTrue(db["tasks"][0]["due"].endswith("08:30"))

    def test_missing_title_fails(self):
        db = fresh_db()
        added, failed, details = import_from_string("| due: 2026-10-13", db, return_details=True)
        self.assertEqual((added, failed), (0, 1))
        self.assertIn("missing title", details[0])

    def test_invalid_due_fails(self):
        db = fresh_db()
        added, failed, details = import_from_string("Task | due: notadate", db, return_details=True)
        self.assertEqual((added, failed), (0, 1))
        self.assertIn("invalid due", details[0])

    def test_invalid_repeat_fails(self):
        db = fresh_db()
        added, failed, details = import_from_string("Task | repeat: fortnightly", db, return_details=True)
        self.assertEqual((added, failed), (0, 1))

    def test_custom_repeat_zero_fails(self):
        db = fresh_db()
        added, failed, details = import_from_string("Task | repeat: custom:0", db, return_details=True)
        self.assertEqual((added, failed), (0, 1))

    def test_comments_and_blanks_skipped(self):
        db = fresh_db()
        added, failed = import_from_string("# a comment\n\nReal task\n", db)
        self.assertEqual((added, failed), (1, 0))

    def test_leading_dash_stripped(self):
        db = fresh_db()
        import_from_string("- Bullet task", db)
        self.assertEqual(db["tasks"][0]["title"], "Bullet task")

    def test_shared_validators_match_the_line_messages(self):
        from tasklistprogram.core.io_import import normalize_repeat, parse_due_or_raise
        self.assertEqual(normalize_repeat(" Bi-Weekly "), "bi-weekly")
        self.assertEqual(normalize_repeat(None), "none")
        self.assertEqual(normalize_repeat("custom: 6"), "custom:6")
        with self.assertRaises(ValueError) as cm:
            normalize_repeat("fortnightly")
        _, _, details = import_from_string("Task | repeat: fortnightly", fresh_db(), return_details=True)
        self.assertEqual(details[0], f"Line 1: {cm.exception}")
        with self.assertRaises(ValueError) as cm:
            parse_due_or_raise("notadate")
        _, _, details = import_from_string("Task | due: notadate", fresh_db(), return_details=True)
        self.assertEqual(details[0], f"Line 1: {cm.exception}")


if __name__ == "__main__":
    unittest.main()
