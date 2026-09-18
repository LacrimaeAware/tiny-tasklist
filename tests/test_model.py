import unittest
from datetime import datetime, date, timedelta

from tasklistprogram.core import model


class SettingsTests(unittest.TestCase):
    def test_defaults_present(self):
        s = model.default_settings()
        for key in ("reminders_enabled", "reminder_count", "min_priority_visible",
                    "ui_category_scope", "ui_time_scope"):
            self.assertIn(key, s)

    def test_normalize_fills_defaults(self):
        s = model.normalize_settings({})
        self.assertEqual(s["ui_category_scope"], "active")
        self.assertEqual(s["ui_time_scope"], "today")

    def test_normalize_keeps_incoming(self):
        s = model.normalize_settings({"reminder_count": 9})
        self.assertEqual(s["reminder_count"], 9)

    def test_migrate_legacy_overdue_scope(self):
        s = model.normalize_settings({"ui_filter_scope": "overdue"})
        self.assertEqual(s["ui_category_scope"], "overdue")
        self.assertEqual(s["ui_time_scope"], "any")

    def test_migrate_legacy_today_scope(self):
        s = model.normalize_settings({"ui_filter_scope": "today"})
        self.assertEqual(s["ui_time_scope"], "today")
        self.assertEqual(s["ui_category_scope"], "active")

    def test_migrate_legacy_done_scope(self):
        s = model.normalize_settings({"ui_filter_scope": "done"})
        self.assertEqual(s["ui_category_scope"], "done")


class StoreTests(unittest.TestCase):
    """SQLite store: fresh load, round-trip, migration, rev, backups — all on a temp dir."""
    PATHS = ("DATA_DIR", "DB_FILE", "DATA_FILE", "BACKUP_FILE", "BACKUP_DIR",
             "LEGACY_DATA_FILE", "LEGACY_BACKUP_FILE")

    def setUp(self):
        import tempfile
        from pathlib import Path
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = {k: getattr(model, k) for k in self.PATHS}
        model.DATA_DIR = self.tmp
        model.DB_FILE = self.tmp / "tasks.db"
        model.DATA_FILE = self.tmp / "tasks_gui.json"
        model.BACKUP_FILE = self.tmp / "tasks_gui.json.bak"
        model.BACKUP_DIR = self.tmp / "backups"
        model.LEGACY_DATA_FILE = self.tmp / "nope.json"
        model.LEGACY_BACKUP_FILE = self.tmp / "nope.bak"

    def tearDown(self):
        for k, v in self._orig.items():
            setattr(model, k, v)

    def _premigration(self):
        return model.DATA_FILE.parent / (model.DATA_FILE.name + ".premigration")

    def test_fresh_load_is_empty(self):
        db = model.load_db()
        self.assertEqual(db["tasks"], [])
        self.assertEqual(db["next_id"], 1)

    def test_save_and_roundtrip(self):
        model.save_db({"version": 1, "next_id": 3, "settings": {"min_priority_visible": "H"},
                       "tasks": [{"id": 1, "title": "a"}, {"id": 2, "title": "b", "notes": "n"}]})
        got = model.load_db()
        self.assertEqual([t["id"] for t in got["tasks"]], [1, 2])
        self.assertEqual(got["next_id"], 3)
        self.assertEqual(got["settings"]["min_priority_visible"], "H")
        self.assertEqual(got["tasks"][1]["notes"], "n")
        self.assertTrue(model.DB_FILE.exists())

    def test_rev_increments_on_save(self):
        model.save_db({"version": 1, "next_id": 1, "tasks": []})
        r1 = model.current_rev()
        model.save_db({"version": 1, "next_id": 1, "tasks": []})
        self.assertEqual(model.current_rev(), r1 + 1)

    def test_migrates_json_and_keeps_premigration(self):
        import json
        payload = {"version": 1, "next_id": 5, "settings": {"ui_theme": "dark"},
                   "tasks": [{"id": 1, "title": "keep", "notes": "n", "history": ["2026-01-01"]}]}
        model.DATA_FILE.write_text(json.dumps(payload), encoding="utf-8")
        db = model.load_db()
        self.assertEqual([t["title"] for t in db["tasks"]], ["keep"])
        self.assertEqual(db["tasks"][0]["history"], ["2026-01-01"])
        self.assertEqual(db["settings"]["ui_theme"], "dark")
        self.assertEqual(db["next_id"], 5)
        self.assertTrue(model.DB_FILE.exists())
        self.assertFalse(model.DATA_FILE.exists())        # original moved aside
        self.assertTrue(self._premigration().exists())    # ...and kept as a safety copy

    def test_migrate_tolerates_utf8_bom(self):
        import json
        model.DATA_FILE.write_text(
            json.dumps({"version": 1, "tasks": [{"id": 1, "title": "x"}], "next_id": 2}),
            encoding="utf-8-sig")
        db = model.load_db()
        self.assertEqual(len(db["tasks"]), 1)


class BackupTests(unittest.TestCase):
    def test_save_creates_daily_backup_and_prunes(self):
        import tempfile
        from pathlib import Path
        tmp = Path(tempfile.mkdtemp())
        orig = (model.DATA_DIR, model.DB_FILE, model.DATA_FILE, model.BACKUP_FILE, model.BACKUP_DIR)
        try:
            model.DATA_DIR = tmp
            model.DB_FILE = tmp / "tasks.db"
            model.DATA_FILE = tmp / "tasks_gui.json"
            model.BACKUP_FILE = tmp / "tasks_gui.json.bak"
            model.BACKUP_DIR = tmp / "backups"
            model.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            # Pre-seed more than the keep limit of old dated backups.
            for i in range(model.DAILY_BACKUPS_KEEP + 5):
                (model.BACKUP_DIR / f"tasks_gui_2020-01-{i+1:02d}.json").write_text("{}", encoding="utf-8")
            model.save_db({"version": 1, "tasks": [], "next_id": 1})
            snaps = sorted(model.BACKUP_DIR.glob("tasks_gui_*.json"))
            self.assertLessEqual(len(snaps), model.DAILY_BACKUPS_KEEP)
            # Today's snapshot exists.
            from datetime import date
            self.assertTrue((model.BACKUP_DIR / f"tasks_gui_{date.today().isoformat()}.json").exists())
        finally:
            model.DATA_DIR, model.DB_FILE, model.DATA_FILE, model.BACKUP_FILE, model.BACKUP_DIR = orig


class TaskHelperTests(unittest.TestCase):
    def test_get_task(self):
        db = {"tasks": [{"id": 1}, {"id": 2}]}
        self.assertEqual(model.get_task(db, 2)["id"], 2)
        self.assertIsNone(model.get_task(db, 99))

    def test_delete_task(self):
        db = {"tasks": [{"id": 1}, {"id": 2}]}
        model.delete_task(db, 1)
        self.assertEqual([t["id"] for t in db["tasks"]], [2])


class StatsTests(unittest.TestCase):
    def test_stats_summary_counts(self):
        now = datetime.now()
        db = {"tasks": [
            {"id": 1, "title": "a", "completed_at": now.isoformat(timespec="seconds"), "repeat": "none"},
            {"id": 2, "title": "b", "completed_at": "", "repeat": "none"},
        ]}
        summary = model.stats_summary(db)
        self.assertEqual(summary["done_today"], 1)
        self.assertEqual(summary["open"], 1)

    def test_stats_streak(self):
        today = date.today()
        hist = [(today - timedelta(days=i)).isoformat() for i in range(1, 4)]
        db = {"tasks": [{"id": 1, "title": "habit", "repeat": "daily", "history": hist, "completed_at": ""}]}
        summary = model.stats_summary(db)
        self.assertTrue(summary["top_streaks"])
        self.assertEqual(summary["top_streaks"][0][1], 3)


if __name__ == "__main__":
    unittest.main()
