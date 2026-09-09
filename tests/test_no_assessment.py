# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Analysis only: part 2 stays out, the measured values stay in.

``assess`` is not a third value of ``lite``. ``lite`` says what the export
supports, ``assess`` says how much the report concludes from it - the two are
independent and combine freely. What the reader gives up with ``assess=False``
is every conclusion: the per-slot verdict, the curve-shape derivations, and the
loop-derived quantities. What is measured stays, CR (CHO/bolus) and the return
delta included, because both are computed from the export rather than judged.
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


class TestNoAssessment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = str(_export(cls.tmp.name))
        cls.html, cls.ctx = core.generate_report(base, lang="de", assess=False)
        cls.full_html, cls.full_ctx = core.generate_report(base, lang="de")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_flag_reaches_the_context(self):
        self.assertFalse(self.ctx["assess"])
        self.assertTrue(self.full_ctx["assess"])

    def test_part_two_is_gone(self):
        for term in ("Teil 2", "CR-Beurteilung pro Slot", "Ableitungen aus der Kurvenform"):
            with self.subTest(term=term):
                self.assertNotIn(term, self.html)

    def test_the_same_export_does_assess_by_default(self):
        """Guards against the report losing part 2 for an unrelated reason."""
        self.assertIn("Teil 2", self.full_html)

    def test_measured_values_stay(self):
        for term in ("AGP", "GRI", "CR (CHO/Bolus)", "Δ4h"):
            with self.subTest(term=term):
                self.assertIn(term, self.html)

    def test_no_verdict_wording_on_the_meals(self):
        """The per-meal table stays, its verdict column does not."""
        self.assertIn("Per-Mahlzeit-Detail", self.html)
        self.assertNotIn("Deckung wirkt", self.html)

    def test_independent_of_lite(self):
        """A lite source is lite either way; assess only removes conclusions."""
        self.assertTrue(self.ctx["lite"])
        self.assertTrue(self.full_ctx["lite"])

    def test_a_full_source_without_basal_still_builds(self):
        """Only part 2 needs the basal trace, so its absence is not fatal here."""
        with tempfile.TemporaryDirectory() as tmp:
            base = _export(tmp)
            # Same data read as a full source: no basal file anywhere in it.
            _html, ctx = core.generate_report(str(base), lang="de", assess=False)
            self.assertFalse(ctx["assess"])

    def test_no_leftover_talk_of_the_clean_subset(self):
        """The clean subset is only ever picked in part 2 - so is its wording."""
        for term in ("sauber", "clean"):
            with self.subTest(term=term):
                self.assertNotIn(term, self.html)
        self.assertIn("clean", self.full_html)

    def test_ugmi_line_is_in_both_modes(self):
        """A footnote about the metrics, not part of the assessment."""
        self.assertIn("uGMI", self.html)
        self.assertIn("uGMI", self.full_html)

    def test_loop_figures_stay_out(self):
        for term in ("CR_eff", "Loop-Mehrbasal", "Auto Mode", "Fasten-Basalrate"):
            with self.subTest(term=term):
                self.assertNotIn(term, self.html)


if __name__ == "__main__":
    unittest.main()
