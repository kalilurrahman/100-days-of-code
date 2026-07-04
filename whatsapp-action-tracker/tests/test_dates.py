import unittest
from datetime import date, datetime

from watracker.dates import find_due_date

REF = datetime(2026, 7, 1, 9, 0)  # a Wednesday


class DueDateTests(unittest.TestCase):
    def check(self, text, expected):
        self.assertEqual(find_due_date(text, REF), expected, text)

    def test_relative(self):
        self.check("please do this today", date(2026, 7, 1))
        self.check("need it by EOD", date(2026, 7, 1))
        self.check("send it tomorrow", date(2026, 7, 2))
        self.check("finish by day after tomorrow", date(2026, 7, 3))

    def test_weekdays(self):
        self.check("send the deck by Friday", date(2026, 7, 3))
        self.check("share it on Monday", date(2026, 7, 6))
        self.check("next Tuesday works", date(2026, 7, 7))

    def test_week_month(self):
        self.check("by end of the week", date(2026, 7, 3))
        self.check("wrap up by end of month", date(2026, 7, 31))
        self.check("let's revisit next week", date(2026, 7, 6))

    def test_in_n(self):
        self.check("follow up in 3 days", date(2026, 7, 4))
        self.check("check back in 2 weeks", date(2026, 7, 15))

    def test_numeric_and_named(self):
        self.check("due 15/7", date(2026, 7, 15))
        self.check("submit by 15/07/2026", date(2026, 7, 15))
        self.check("launch on 9 July", date(2026, 7, 9))
        self.check("launch on July 9th", date(2026, 7, 9))

    def test_past_named_date_rolls_forward(self):
        self.check("bill due 5 January", date(2027, 1, 5))

    def test_none(self):
        self.assertIsNone(find_due_date("no deadline mentioned here", REF))


if __name__ == "__main__":
    unittest.main()
