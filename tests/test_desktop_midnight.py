"""The desktop midnight reset must not overwrite edits the web server saved meanwhile.

These tests import the Tkinter app module but never create a window: the methods
under test are called on an instance made with __new__, with the store functions
they use replaced by mocks.
"""
import unittest
from datetime import date, timedelta
from unittest import mock

try:
    from tasklistprogram import app as desktop
except Exception:  # tkinter not available on this interpreter
    desktop = None


def iso(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).strftime("%Y-%m-%d")


@unittest.skipIf(desktop is None, "tkinter not available")
class MidnightResetReloadTests(unittest.TestCase):
    def _window(self, db):
        win = desktop.TaskApp.__new__(desktop.TaskApp)  # no Tk root
        win.db = db
        win.refresh = lambda: None
        win.schedule_midnight_reset = lambda: None
        return win

    def test_reloads_before_advancing_when_the_store_moved(self):
        stale = {"_rev": 1, "settings": {}, "tasks": [
            {"id": 1, "title": "old title", "repeat": "daily", "due": iso(-1), "completed_at": "", "skip_count": 0}]}
        fresh = {"_rev": 2, "settings": {}, "tasks": [
            {"id": 1, "title": "edited in the browser", "repeat": "daily", "due": iso(-1), "completed_at": "", "skip_count": 0}]}
        with mock.patch.object(desktop, "current_rev", return_value=2), \
             mock.patch.object(desktop, "load_db", return_value=fresh) as load, \
             mock.patch.object(desktop, "save_db") as save:
            win = self._window(stale)
            win.reset_repeating_tasks(catchup=False)
        load.assert_called_once()
        self.assertIs(win.db, fresh)
        save.assert_called_once_with(fresh)
        self.assertEqual(fresh["tasks"][0]["title"], "edited in the browser")
        self.assertEqual(fresh["tasks"][0]["due"], iso(0))

    def test_no_reload_and_no_save_when_nothing_moved_or_advanced(self):
        db = {"_rev": 7, "settings": {}, "tasks": [
            {"id": 1, "title": "future", "repeat": "daily", "due": iso(3), "completed_at": "", "skip_count": 0}]}
        with mock.patch.object(desktop, "current_rev", return_value=7), \
             mock.patch.object(desktop, "load_db") as load, \
             mock.patch.object(desktop, "save_db") as save:
            win = self._window(db)
            win.reset_repeating_tasks(catchup=True)
        load.assert_not_called()
        save.assert_not_called()
        self.assertIs(win.db, db)

    def test_unreadable_revision_keeps_working_with_the_in_memory_copy(self):
        db = {"_rev": 1, "settings": {}, "tasks": [
            {"id": 1, "title": "t", "repeat": "daily", "due": iso(-2), "completed_at": "", "skip_count": 0}]}
        with mock.patch.object(desktop, "current_rev", return_value=None), \
             mock.patch.object(desktop, "load_db") as load, \
             mock.patch.object(desktop, "save_db") as save:
            win = self._window(db)
            win.reset_repeating_tasks(catchup=True)
        load.assert_not_called()
        save.assert_called_once_with(db)
        self.assertEqual(db["tasks"][0]["due"], iso(0))


if __name__ == "__main__":
    unittest.main()
