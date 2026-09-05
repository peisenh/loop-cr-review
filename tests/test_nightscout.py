import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import loop_cr_review as core
from lcr.readers.nightscout import _ns_offset_minutes, read_nightscout


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


class TestDaylightSaving(unittest.TestCase):
    """A range that crosses the clock change, which a real export does.

    Regression: the offset was taken from the first record and applied to every
    other one. The first record is the oldest, so a six-month range starting in
    March carried the winter offset into every summer day and each reading came
    out an hour early. Found on a real 180 day export where the offsets were
    120 (119914 records), 60 (15309) and 0 (3053).
    """

    @staticmethod
    def _reading(day, hour, offset, stated=None):
        """A reading taken at *hour* local time in a zone *offset* minutes east."""
        stamp = (datetime(2026, *day, hour, tzinfo=timezone.utc)
                 - timedelta(minutes=offset))
        return {"type": "sgv", "sgv": 120,
                "utcOffset": offset if stated is None else stated,
                "dateString": stamp.isoformat().replace("+00:00", "Z"),
                "date": int(stamp.timestamp() * 1000)}

    def _read(self, entries, treatments=()):
        folder = Path(tempfile.mkdtemp())
        (folder / "entries.json").write_text(json.dumps(entries), encoding="utf-8")
        (folder / "treatments.json").write_text(json.dumps(list(treatments)),
                                                encoding="utf-8")
        return read_nightscout(folder)

    def test_winter_and_summer_readings_keep_their_own_clock(self):
        entries = ([self._reading((3, 16), 8, 60)]
                   + [self._reading((8, 22), 8, 120) for _ in range(3)])
        result = self._read(entries)
        hours = sorted({t.hour for t in result["times"]})
        self.assertEqual(hours, [8], "every reading was taken at 8 local time")

    def test_a_record_without_an_offset_uses_the_common_one(self):
        """Uploaders that do not track the wearer's zone write a zero."""
        entries = ([self._reading((8, 22), 8, 120) for _ in range(3)]
                   + [self._reading((8, 23), 8, 120, stated=0)])
        result = self._read(entries)
        self.assertEqual(sorted({t.hour for t in result["times"]}), [8])

    def test_the_fallback_is_the_common_offset_not_the_first(self):
        entries = ([self._reading((3, 16), 8, 60)]
                   + [self._reading((8, 22), 8, 120) for _ in range(5)])
        self.assertEqual(_ns_offset_minutes(entries), 120)

    def test_a_meal_keeps_the_hour_it_was_eaten(self):
        stamp = datetime(2026, 8, 22, 22, tzinfo=timezone.utc) - timedelta(minutes=120)
        meal = {"eventType": "Meal Bolus", "carbs": 60, "insulin": 5.0,
                "utcOffset": 120,
                "created_at": stamp.isoformat().replace("+00:00", "Z")}
        entries = [self._reading((8, 22), h, 120) for h in (20, 21, 22, 23)]
        result = self._read(entries, [meal])
        self.assertEqual([m["time"].hour for m in result["meals"]], [22])
