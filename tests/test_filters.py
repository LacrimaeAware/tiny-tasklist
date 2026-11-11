import unittest
from datetime import datetime, date, timedelta

from tasklistprogram.core import filters


def task(**kw):
    base = {"id": 1, "title": "t", "notes": "", "priority": "M", "due": "", "repeat": "none",
            "completed_at": "", "is_deleted": False, "is_suspended": False}
    base.update(kw)
    return base


def due_in(days):
    return (date.today() + timedelta(days=days)).strftime("%Y-%m-%d")


class PriorityVisibleTests(unittest.TestCase):
    def test_at_or_above_threshold_visible(self):
        self.assertTrue(filters.priority_visible(task(priority="H"), {"min_priority_visible": "M"}))
        self.assertTrue(filters.priority_visible(task(priority="M"), {"min_priority_visible": "M"}))

    def test_below_threshold_hidden(self):
        self.assertFalse(filters.priority_visible(task(priority="L"), {"min_priority_visible": "M"}))

    def test_misc_threshold(self):
        # With min "Misc" (X), everything is visible.
        self.assertTrue(filters.priority_visible(task(priority="L"), {"min_priority_visible": "Misc"}))


class CategoryFilterTests(unittest.TestCase):
    def test_active_hides_done_deleted_suspended(self):
        self.assertFalse(filters.passes_category_filter(task(completed_at="2026-01-01T00:00:00"), "active"))
        self.assertFalse(filters.passes_category_filter(task(is_deleted=True), "active"))
        self.assertFalse(filters.passes_category_filter(task(is_suspended=True), "active"))
        self.assertTrue(filters.passes_category_filter(task(), "active"))

    def test_done_scope(self):
        self.assertTrue(filters.passes_category_filter(task(completed_at="x"), "done"))
        self.assertFalse(filters.passes_category_filter(task(), "done"))

    def test_deleted_scope(self):
        self.assertTrue(filters.passes_category_filter(task(is_deleted=True), "deleted"))

    def test_repeating_scope(self):
        self.assertTrue(filters.passes_category_filter(task(repeat="daily"), "repeating"))
        self.assertFalse(filters.passes_category_filter(task(repeat="none"), "repeating"))

    def test_overdue_scope(self):
        self.assertTrue(filters.passes_category_filter(task(due=due_in(-2)), "overdue"))
        self.assertFalse(filters.passes_category_filter(task(due=due_in(5)), "overdue"))


class TimeFilterTests(unittest.TestCase):
    def test_any_shows_all(self):
        self.assertTrue(filters.passes_time_filter(task(due=""), "active", "any"))

    def test_today_hides_no_due(self):
        self.assertFalse(filters.passes_time_filter(task(due=""), "active", "today"))

    def test_today_includes_overdue(self):
        self.assertTrue(filters.passes_time_filter(task(due=due_in(-3)), "active", "today"))

    def test_today_includes_today(self):
        self.assertTrue(filters.passes_time_filter(task(due=due_in(0)), "active", "today"))

    def test_today_excludes_future(self):
        self.assertFalse(filters.passes_time_filter(task(due=due_in(5)), "active", "today"))

    def test_week(self):
        self.assertTrue(filters.passes_time_filter(task(due=due_in(5)), "active", "week"))
        self.assertFalse(filters.passes_time_filter(task(due=due_in(20)), "active", "week"))

    def test_custom(self):
        cutoff = date.today() + timedelta(days=10)
        self.assertTrue(filters.passes_time_filter(task(due=due_in(5)), "active", "custom", cutoff))
        self.assertFalse(filters.passes_time_filter(task(due=due_in(15)), "active", "custom", cutoff))
        self.assertFalse(filters.passes_time_filter(task(due=due_in(5)), "active", "custom", None))

    def test_archived_views_ignore_time(self):
        self.assertTrue(filters.passes_time_filter(task(due=""), "done", "today"))


class SearchAndSortTests(unittest.TestCase):
    def test_search_matches_title_and_notes(self):
        self.assertTrue(filters.search_match(task(title="Buy milk"), "milk"))
        self.assertTrue(filters.search_match(task(notes="call the vet"), "vet"))
        self.assertFalse(filters.search_match(task(title="abc", notes="def"), "zzz"))
        self.assertTrue(filters.search_match(task(), ""))

    def test_sort_key_due_empty_sorts_last(self):
        self.assertEqual(filters.sort_key_for(task(due=""), "due"), datetime.max)

    def test_sort_key_priority(self):
        self.assertGreater(
            filters.sort_key_for(task(priority="H"), "prio"),
            filters.sort_key_for(task(priority="L"), "prio"),
        )


if __name__ == "__main__":
    unittest.main()
