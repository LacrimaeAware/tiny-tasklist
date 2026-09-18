import unittest
from datetime import datetime, date, timedelta

from tasklistprogram.core import dates


class ParseDueEntryTests(unittest.TestCase):
    def test_bare_time_colon(self):
        result = dates.parse_due_entry("14:30")
        self.assertIsInstance(result, datetime)
        self.assertEqual((result.hour, result.minute), (14, 30))
        self.assertEqual(result.date(), date.today())

    def test_bare_time_hhmm(self):
        result = dates.parse_due_entry("0830")
        self.assertEqual((result.hour, result.minute), (8, 30))

    def test_bare_time_three_digits(self):
        result = dates.parse_due_entry("930")
        self.assertEqual((result.hour, result.minute), (9, 30))

    def test_bare_time_out_of_range_is_none(self):
        self.assertIsNone(dates.parse_due_entry("2599"))

    def test_delegates_to_flexible(self):
        self.assertEqual(dates.fmt_due_for_store(dates.parse_due_entry("2026-10-05")), "2026-10-05")

    def test_empty(self):
        self.assertIsNone(dates.parse_due_entry(""))
        self.assertIsNone(dates.parse_due_entry(None))


class ParseFlexibleTests(unittest.TestCase):
    def test_absolute_date(self):
        self.assertEqual(dates.fmt_due_for_store(dates.parse_due_flexible("2026-10-05")), "2026-10-05")

    def test_absolute_datetime(self):
        self.assertEqual(
            dates.fmt_due_for_store(dates.parse_due_flexible("2026-10-05 14:00")), "2026-10-05 14:00"
        )

    def test_mmdd_current_year(self):
        out = dates.fmt_due_for_store(dates.parse_due_flexible("10/05"))
        self.assertEqual(out, f"{datetime.now().year}-10-05")

    def test_mmdd_invalid(self):
        self.assertIsNone(dates.parse_due_flexible("13/45"))

    def test_midnight(self):
        result = dates.parse_due_flexible("midnight")
        self.assertEqual((result.hour, result.minute), (23, 59))

    def test_daypart(self):
        result = dates.parse_due_flexible("morning")
        self.assertEqual((result.hour, result.minute), (8, 0))

    def test_weekday(self):
        result = dates.parse_due_flexible("fri")
        self.assertIsNotNone(result)
        # Returns a date-only tuple for the upcoming Friday.
        _, dt = result
        self.assertEqual(dt.weekday(), 4)

    def test_relative_days(self):
        result = dates.parse_due_flexible("+2d")
        self.assertIsInstance(result, tuple)
        _, dt = result
        self.assertEqual(dt.date(), date.today() + timedelta(days=2))

    def test_relative_with_time(self):
        result = dates.parse_due_flexible("+2d +3h")
        self.assertIsInstance(result, datetime)

    def test_mixed_styles_rejected(self):
        self.assertIsNone(dates.parse_due_flexible("+1w friday"))

    def test_today_tomorrow_yesterday(self):
        _, t_today = dates.parse_due_flexible("today")
        self.assertEqual(t_today.date(), date.today())
        _, t_tom = dates.parse_due_flexible("tomorrow")
        self.assertEqual(t_tom.date(), date.today() + timedelta(days=1))
        _, t_yes = dates.parse_due_flexible("yesterday")
        self.assertEqual(t_yes.date(), date.today() - timedelta(days=1))

    def test_tomorrow_with_time(self):
        result = dates.parse_due_flexible("tomorrow 14:00")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.date(), date.today() + timedelta(days=1))
        self.assertEqual((result.hour, result.minute), (14, 0))

    def test_month_name(self):
        out = dates.fmt_due_for_store(dates.parse_due_flexible("Sept 29"))
        self.assertEqual(out, f"{datetime.now().year}-09-29")

    def test_month_name_full_with_year(self):
        out = dates.fmt_due_for_store(dates.parse_due_flexible("September 29 2027"))
        self.assertEqual(out, "2027-09-29")

    def test_month_name_with_time(self):
        result = dates.parse_due_flexible("dec 1 09:00")
        self.assertIsInstance(result, datetime)
        self.assertEqual((result.month, result.day, result.hour), (12, 1, 9))


class RecurrenceTests(unittest.TestCase):
    def test_next_due_variants(self):
        base = date(2026, 1, 1)
        self.assertEqual(dates.next_due(base, "daily"), date(2026, 1, 2))
        self.assertEqual(dates.next_due(base, "weekly"), date(2026, 1, 8))
        self.assertEqual(dates.next_due(base, "bi-weekly"), date(2026, 1, 15))
        self.assertEqual(dates.next_due(base, "custom:6"), date(2026, 1, 7))
        self.assertEqual(dates.next_due(base, "monthly"), date(2026, 2, 1))

    def test_next_due_weekdays_skips_weekend(self):
        friday = date(2026, 1, 2)  # a Friday
        self.assertEqual(dates.next_due(friday, "weekdays"), date(2026, 1, 5))  # Monday

    def test_next_due_none(self):
        base = date(2026, 1, 1)
        self.assertEqual(dates.next_due(base, "none"), base)

    def test_repeat_interval_days(self):
        self.assertEqual(dates.repeat_interval_days("weekly"), 7)
        self.assertEqual(dates.repeat_interval_days("bi-weekly"), 14)
        self.assertEqual(dates.repeat_interval_days("custom:9"), 9)
        self.assertIsNone(dates.repeat_interval_days("custom:0"))
        self.assertIsNone(dates.repeat_interval_days("monthly"))

    def test_month_add_clamps_day(self):
        self.assertEqual(dates.month_add(date(2026, 1, 31)), date(2026, 2, 28))

    def test_month_add_year_rollover(self):
        self.assertEqual(dates.month_add(date(2026, 12, 15)), date(2027, 1, 15))

    def test_add_months_alias(self):
        self.assertEqual(dates.add_months_dateonly(date(2026, 1, 31)), dates.month_add(date(2026, 1, 31)))


if __name__ == "__main__":
    unittest.main()
