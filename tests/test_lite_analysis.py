# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sources without a basal rate still get the full assessment.

Everything the glucose curve alone can say applies to them too: the return
delta, the verdict that follows from it, and every derivation from the curve
shape. Only what needs a basal trace - the loop extra basal and CR_eff - stays
out. Before this the whole of Part 2 was dropped for them, although the data
for most of it was there.
"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import loop_cr_review as core   # noqa: E402  pylint: disable=wrong-import-position

CLARITY_HEAD = (
    "Index,Timestamp (YYYY-MM-DDThh:mm:ss),Event Type,Event Subtype,Patient Info,"
    "Device Info,Source Device ID,Glucose Value (mg/dL),Insulin Value (u),"
    "Carb Value (grams),Duration (hh:mm:ss),Glucose Rate of Change (mg/dL/min),"
    "Transmitter Time (Long Integer),Transmitter ID\n")


def _export(directory, days=12, rise=90):
    """A Clarity export with one lunch a day that ends clearly high."""
    rows, index = [], 10
    start = datetime(2026, 5, 1, 0, 0)
    for day in range(days):
        base = start + timedelta(days=day)
        for step in range(288):                      # a full day of 5-minute values
            stamp = base + timedelta(minutes=5 * step)
            minutes_after = (stamp - (base + timedelta(hours=12))).total_seconds() / 60
            value = 110
            if 0 <= minutes_after <= 240:            # the meal excursion
                value = 110 + rise * min(1.0, minutes_after / 90)
            rows.append(f"{index},{stamp:%Y-%m-%dT%H:%M:%S},EGV,,,,iPhone,{value:.0f},,,,,1,X\n")
            index += 1
        meal = base + timedelta(hours=12)
        rows.append(f"{index},{meal:%Y-%m-%dT%H:%M:%S},Carbs,,,,iPhone,,,60,,,,\n"); index += 1
        rows.append(f"{index},{meal:%Y-%m-%dT%H:%M:%S},Insulin,Fast-Acting,,,iPhone,,6,,,,,\n")
        index += 1
    path = Path(directory) / "clarity.csv"
    path.write_text(CLARITY_HEAD + "".join(rows), encoding="utf-8-sig")
    return Path(directory)


class TestLiteStillAssesses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.html, cls.ctx = core.generate_report(str(_export(cls.tmp.name)), lang="de")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_slots_are_assessed(self):
        self.assertTrue(self.ctx["slots"], "no slot assessment without basal")

    def test_a_clearly_high_return_is_called_weak(self):
        """+90 mg/dL after four hours is past the threshold, basal or not."""
        lunch = [s for s in self.ctx["slots"] if s["n"]][0]
        self.assertEqual(lunch["cls"], "weak")

    def test_derivations_are_present(self):
        self.assertTrue(self.ctx["recs"], "curve-shape derivations dropped")

    def test_no_loop_wording_leaks_in(self):
        for term in ("CR_eff", "Loop-Mehrbasal", "Auto Mode"):
            with self.subTest(term=term):
                self.assertNotIn(term, self.html)

    def test_stability_is_computed(self):
        self.assertTrue(any(s.get("stability") for s in self.ctx["slots"]))

    def test_contamination_is_detected_without_basal(self):
        """It only needs meal times and glucose - it used to be hardcoded False."""
        rows = core.analyze_meals(
            [{"time": datetime(2026, 5, 1, 12, 0), "cho": 60, "bolus": 6, "bg": None},
             {"time": datetime(2026, 5, 1, 14, 0), "cho": 40, "bolus": 4, "bg": None}],
            [], None, 240, lambda t, m: float("nan"))
        self.assertTrue(rows[0]["contam"])


if __name__ == "__main__":
    unittest.main()
