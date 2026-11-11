"""Desktop logic integration on invented tasks, without creating a Tk window."""
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

from tasklistprogram.app import TaskApp
from tasklistprogram.core.actions import ActionsMixin
from tasklistprogram.core import documents, model


class DesktopStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name)
        model_paths = {
            "DATA_DIR": self.data, "DB_FILE": self.data / "tasks.db",
            "DATA_FILE": self.data / "tasks_gui.json",
            "BACKUP_FILE": self.data / "tasks_gui.json.bak",
            "BACKUP_DIR": self.data / "backups",
            "LEGACY_DATA_FILE": self.data / "absent-legacy.json",
            "LEGACY_BACKUP_FILE": self.data / "absent-legacy.bak",
        }
        self.enterContext(mock.patch.multiple(model, **model_paths))
        self.enterContext(mock.patch.multiple(
            documents, DATA_DIR=self.data,
            TASKS_DIR=self.data / "task_documents", JOURNALS_DIR=self.data / "journals"))

    def test_recurring_completion_saves_history_next_due_and_journal(self):
        today = date.today()
        task = {"id": 1, "title": "Read ten pages", "notes": "One question.",
                "group": "Study", "due": today.isoformat(), "repeat": "daily",
                "priority": "D", "completed_at": "", "history": [],
                "times_completed": 0, "skip_count": 0}
        db = model.load_db()
        db["tasks"] = [task]
        db["next_id"] = 2
        window = SimpleNamespace(db=db, selected_tasks=lambda: [task], refresh=mock.Mock())

        ActionsMixin.mark_done(window)

        stored = model.load_db()["tasks"][0]
        self.assertEqual(stored["due"], (today + timedelta(days=1)).isoformat())
        self.assertEqual(stored["history"], [today.isoformat()])
        self.assertEqual(stored["completed_at"], "")
        self.assertEqual(model.stats_summary(model.load_db())["done_today"], 1)
        journal = next((self.data / "journals").rglob("*.md"))
        self.assertIn("Completed: Read ten pages", journal.read_text(encoding="utf-8"))
        window.refresh.assert_called_once()

    def test_note_sync_preserves_file_only_section_and_reads_external_edit(self):
        task = {"id": 1, "title": "Draft", "group": "Study", "notes": "First note."}
        path = documents.sync_task_notes(task)
        path.write_text("Updated in file." + documents.TASK_DIVIDER + "Extra detail.\n", encoding="utf-8")
        self.assertTrue(documents.read_task_notes_from_file(task))
        self.assertEqual(task["notes"], "Updated in file.")
        task["notes"] = "Revised in app."
        documents.sync_task_notes(task)
        self.assertEqual(path.read_text(encoding="utf-8"),
                         "Revised in app." + documents.TASK_DIVIDER + "Extra detail.\n")

    def test_regrouping_moves_task_document_inside_selected_store(self):
        task = {"id": 1, "title": "Draft", "group": "Study", "notes": "A note."}
        old_path = documents.sync_task_notes(task)
        task["group"] = "Creative"
        new_path = documents.move_task_document_if_needed(task)
        self.assertFalse(old_path.exists())
        self.assertTrue(new_path.is_relative_to(self.data / "task_documents"))
        self.assertEqual(new_path.parent.name, "Creative")
        self.assertIn("A note.", new_path.read_text(encoding="utf-8"))


class DesktopStatusTests(unittest.TestCase):
    def test_status_counts_recurring_history_and_omits_inactive_tasks(self):
        today = date.today().isoformat()
        completed = datetime.now().isoformat(timespec="seconds")
        db = {"tasks": [
            {"title": "Habit", "repeat": "daily", "completed_at": "", "history": [today]},
            {"title": "One-off", "repeat": "none", "completed_at": completed},
            {"title": "Deleted", "repeat": "none", "completed_at": completed, "is_deleted": True},
            {"title": "Suspended", "repeat": "daily", "history": [today], "is_suspended": True},
        ]}
        status = mock.Mock()
        window = SimpleNamespace(db=db, status_var=status)
        TaskApp._update_status(window, shown=1)
        status.set.assert_called_once_with("Showing 1   ·   Open 1   ·   Done today 2")
