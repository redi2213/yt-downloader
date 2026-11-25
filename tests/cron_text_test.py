import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import cron_text  # noqa: E402


class CronTextTest(unittest.TestCase):
    def test_find_crons_skips_comments(self):
        text = "on:\n  schedule:\n    - cron: '0 3 * * *'\n    # - cron: '1 1 * * *'\n    - cron: \"*/15 * * * *\"\n"
        self.assertEqual(cron_text.find_crons(text), ["0 3 * * *", "*/15 * * * *"])

    def test_daily_local_time(self):
        self.assertEqual(cron_text.describe("0 3 * * *", 210), "Every day at 06:30")
        self.assertEqual(cron_text.describe("0 3 * * *", 210, fa=True), "هر روز ساعت ۰۶:۳۰")

    def test_weekly_day_shift(self):
        self.assertEqual(cron_text.describe("30 20 * * 1", 210), "Every Tuesday at 00:00")

    def test_steps(self):
        self.assertEqual(cron_text.describe("*/15 * * * *", 210), "Every 15 minutes")
        self.assertEqual(cron_text.describe("0 */6 * * *", 210), "Every 6 hours, at minute 30")
        self.assertEqual(cron_text.describe("0 * * * *", 0), "Every hour")

    def test_monthly_and_unknown(self):
        self.assertEqual(cron_text.describe("0 0 5 * *", 0), "Every month on day 5 at 00:00")
        self.assertEqual(cron_text.describe("0 0 * 6 *", 0), "0 0 * 6 *")


if __name__ == "__main__":
    unittest.main()
