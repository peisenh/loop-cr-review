"""Basal in rest by time of day: what the loop gave while nothing needed covering.

Built on a hand-made month: 1.4 U/h from midnight to seven, 0.8 U/h after,
steady glucose, and meals at 08:00, 13:00 and 19:00 every day. The rest the
report finds there, and the rates in it, can be worked out by hand.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta

import loop_cr_review as core
from lcr.analysis import rest_basal

START = datetime(2026, 5, 1)
MEAL_HOURS = (8, 13, 19)


def _month(days=20, glucose=120.0, night=1.4, day=0.8):
    """Basal tuple, readings every 5 min, and every meal time. -> (basal, times, gluc, acts)"""
    minutes = days * 1440
    rate = [night if (START + timedelta(minutes=i)).hour < 7 else day for i in range(minutes)]
    basal = (rate, START, minutes, night, night, night)
    times = [START + timedelta(minutes=5 * i) for i in range(minutes // 5)]
    gluc = [glucose] * len(times)
    acts = [START + timedelta(days=d, hours=h) for d in range(days) for h in MEAL_HOURS]
    return basal, times, gluc, acts


def _block(prof, start):
    """The block that starts at *start* o'clock. -> dict"""
    return next(b for b in prof["blocks"] if b["start"] == start)


class TestRestBasal(unittest.TestCase):
    """Rest is 6 h after a meal, readings in range and steady."""

    def setUp(self):
        core.setup_i18n("en")
        self.prof = rest_basal(*_month())

    def test_night_rate_in_rest(self):
        """The 19:00 meal is six hours old at one: 01-07 is rest at 1.4 U/h."""
        self.assertAlmostEqual(_block(self.prof, 3)["mean"], 1.4, places=9)
        self.assertAlmostEqual(_block(self.prof, 0)["mean"], 1.4, places=9)
        # 00:45-01:00 is the first quarter hour that ends six hours after it.
        self.assertAlmostEqual(self.prof["hours"][0]["hours"], 19 * 0.25, places=9)
        self.assertAlmostEqual(self.prof["hours"][1]["hours"], 19 * 1.0, places=9)

    def test_morning_before_breakfast_is_rest(self):
        """07-08 is rest at the day rate; after breakfast only the quarter hour
        that ends six hours after lunch, 18:45-19:00, until 00:45."""
        self.assertAlmostEqual(self.prof["hours"][7]["mean"], 0.8, places=9)
        for hour in (*range(8, 18), *range(19, 24)):
            self.assertIsNone(self.prof["hours"][hour], hour)
        self.assertAlmostEqual(self.prof["hours"][18]["hours"], 20 * 0.25, places=9)
        self.assertIsNone(_block(self.prof, 11)["mean"])
        self.assertEqual(_block(self.prof, 11)["days"], 0)

    def test_delivered_counts_every_quarter_hour(self):
        """The upper bound is the rate itself here, rest or not."""
        self.assertAlmostEqual(self.prof["delivered"][3], 1.4, places=9)
        self.assertAlmostEqual(self.prof["delivered"][20], 0.8, places=9)

    def test_first_hours_of_the_range_are_not_rest(self):
        """A bolus just before the range is not in the list, so the start waits."""
        basal, times, gluc, acts = _month()
        prof = rest_basal(basal, times, gluc, acts)
        self.assertEqual(prof["hours"][3]["days"], 19, "day one starts at 06:00")
        self.assertEqual(prof["hours"][6]["days"], 20)

    def test_high_glucose_is_no_rest(self):
        """Above 180 mg/dL the loop is correcting, not resting."""
        self.assertIsNone(rest_basal(*_month(glucose=200.0)))

    def test_unsteady_glucose_is_no_rest(self):
        """In range but rising: the loop is at work, not at rest."""
        basal, times, _gluc, acts = _month()
        # 1 mg/dL a minute, back down every hour: 30 mg/dL over any half hour.
        rising = [100.0 + (i % 12) * 5 for i in range(len(times))]
        self.assertIsNone(rest_basal(basal, times, rising, acts))

    def test_short_export_says_nothing(self):
        """Under 14 days one fortnight's pattern looked like a rule."""
        self.assertIsNone(rest_basal(*_month(days=10)))

    def test_mean_not_median(self):
        """A loop that throttles three quarter hours and gives a lot in the fourth."""
        basal, times, gluc, acts = _month()
        rate = basal[0]
        for i, _old in enumerate(rate):
            if (START + timedelta(minutes=i)).hour < 7:
                rate[i] = 4.0 if (i // 15) % 4 == 0 else 0.0
        prof = rest_basal(basal, times, gluc, acts)
        self.assertAlmostEqual(_block(prof, 3)["mean"], 1.0, places=9)
        self.assertEqual(prof["hours"][3]["median"], 0.0)


class TestRestBasalInReport(unittest.TestCase):
    """The card sits in part 2 and only where the export carries basal."""

    def test_example_report_has_the_card(self):
        """The Glooko example spans 14 days with basal: the card is there."""
        html, ctx = core.generate_report("example-data", lang="en")
        self.assertIsNotNone(ctx["rest_basal"])
        self.assertIn("Basal in rest by time of day", html)
        self.assertIn("not a basal profile to programme", html)

    def test_german_card(self):
        """Title and text come from the catalogue."""
        html, _ctx = core.generate_report("example-data", lang="de")
        self.assertIn("Basal in Ruhephasen nach Tageszeit", html)

    def test_no_card_without_assessment(self):
        """Without part 2 there is nothing the card is context for."""
        html, ctx = core.generate_report("example-data", lang="en", assess=False)
        self.assertIsNone(ctx["rest_basal"])
        self.assertNotIn("Basal in rest by time of day", html)


if __name__ == "__main__":
    unittest.main()
