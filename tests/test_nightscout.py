import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import loop_cr_review as core


def _dump(folder, entries, treatments):
    Path(folder, "entries.json").write_text(json.dumps(entries), encoding="utf-8")
    Path(folder, "treatments.json").write_text(json.dumps(treatments), encoding="utf-8")


class TestNightscout(unittest.TestCase):
    def test_offset_shifts_utc_to_local_naive(self):
        obj = {"dateString": "2026-08-21T10:00:00.000Z"}
        ts = core._ns_parse_time(obj, 120)
        self.assertEqual(ts, datetime(2026, 8, 21, 12, 0, 0))

    def test_treatment_offset_ignored(self):
        obj = {"created_at": "2026-08-21T10:00:00.000Z", "utcOffset": 0}
        ts = core._ns_parse_time(obj, 120)
        self.assertEqual(ts, datetime(2026, 8, 21, 12, 0, 0))

    def test_reads_meal_and_temp(self):
        t0 = 1787304000000  # dummy; dateString used
        entries = [
            {"type": "sgv", "sgv": 110, "dateString": "2026-08-21T08:00:00.000Z",
             "utcOffset": 120, "date": t0},
            {"type": "sgv", "sgv": 112, "dateString": "2026-08-21T08:05:00.000Z",
             "utcOffset": 120, "date": t0 + 300000},
        ]
        treatments = [
            {"eventType": "Meal Bolus", "created_at": "2026-08-21T08:00:00.000Z",
             "carbs": 50, "insulin": 5, "utcOffset": 0},
            {"eventType": "Temp Basal", "created_at": "2026-08-21T07:00:00.000Z",
             "rate": 1.0, "duration": 180, "utcOffset": 0},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            _dump(tmp, entries, treatments)
            data = core.read_nightscout(tmp)
            self.assertEqual(len(data["times"]), 2)
            self.assertEqual(len(data["meals"]), 1)
            self.assertEqual(data["meals"][0]["cho"], 50)
            self.assertIsNotNone(data["basal"])
            html, ctx = core.generate_report(tmp, lang="en")
            self.assertEqual(ctx["source"], "nightscout")
            self.assertTrue(ctx["lite"])
            self.assertIn("Per-meal", html)
            self.assertNotIn("How to read this report (CamAPS", html)
            html2, ctx2 = core.generate_report(tmp, lang="en", assume_camaps=True)
            self.assertFalse(ctx2["lite"])
            self.assertIn("How to read this report (CamAPS", html2)
