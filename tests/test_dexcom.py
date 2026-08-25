# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading a Dexcom Clarity export.

The fixtures below are written by hand rather than taken from a real export:
the public sample files are real patient data under no licence, so they are
fine for trying a parser out but not for shipping in a repository.
"""
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import loop_cr_review as core   # noqa: E402  pylint: disable=wrong-import-position

HEADER = ("Index,Timestamp (YYYY-MM-DDThh:mm:ss),Event Type,Event Subtype,Patient Info,"
          "Device Info,Source Device ID,Glucose Value ({unit}),Insulin Value (u),"
          "Carb Value (grams),Duration (hh:mm:ss),Glucose Rate of Change ({unit}/min),"
          "Transmitter Time (Long Integer),Transmitter ID")

# The rows an export starts with: name, device, alert thresholds. None of them
# carry data, and the alert rows put numbers in the glucose column.
META = ("1,,FirstName,,Ada,,,,,,,,,\n"
        "2,,LastName,,Lovelace,,,,,,,,,\n"
        "3,,Device,,,Dexcom G7 Mobile App,iPhone G7,,,,,,,\n"
        "4,,Alert,High,,,iPhone G7,200,,,,,,\n"
        "5,,Alert,Urgent Low,,,iPhone G7,55,,,,,,\n")


def write_export(directory, body, unit="mg/dL", meta=META):
    """Write a Clarity-style CSV and return its directory."""
    path = Path(directory) / "clarity_export.csv"
    path.write_text(HEADER.format(unit=unit) + "\n" + meta + body,
                    encoding="utf-8-sig")
    return Path(directory)


def egv(index, stamp, value):
    return f"{index},{stamp},EGV,,,,iPhone G7,{value},,,,,2899574,8KJ4NS\n"


class TestDexcomReader(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _read(self, body, **kwargs):
        return core.read_dexcom(write_export(self.tmp.name, body, **kwargs))

    def test_detects_the_export(self):
        write_export(self.tmp.name, egv(11, "2026-05-01T08:00:00", 120))
        self.assertTrue(core.is_dexcom(Path(self.tmp.name)))

    def test_does_not_claim_a_foreign_csv(self):
        path = Path(self.tmp.name) / "other.csv"
        path.write_text("Zeitstempel,Wert\n01.05.2026 08:00,120\n", encoding="utf-8")
        self.assertFalse(core.is_dexcom(Path(self.tmp.name)))

    def test_reads_glucose_and_skips_the_meta_rows(self):
        """The alert rows carry numbers in the glucose column — they are settings."""
        body = "".join(egv(10 + i, f"2026-05-01T08:{i:02d}:00", 100 + i) for i in range(5))
        data = self._read(body)
        self.assertEqual(len(data["times"]), 5)
        self.assertEqual(list(data["gluc"]), [100, 101, 102, 103, 104])
        self.assertNotIn(200, data["gluc"])   # the High alert threshold
        self.assertNotIn(55, data["gluc"])    # the Urgent Low threshold

    def test_name_and_device_come_from_the_meta_rows(self):
        data = self._read(egv(11, "2026-05-01T08:00:00", 120))
        self.assertEqual(data["name"], "Ada Lovelace")
        self.assertEqual(data["sensor"], "Dexcom G7 Mobile App")

    def test_low_and_high_become_the_limit(self):
        """Below 40 the sensor reports a word; dropping it would look like a gap."""
        body = (egv(11, "2026-05-01T08:00:00", "Low")
                + egv(12, "2026-05-01T08:05:00", "High")
                + egv(13, "2026-05-01T08:10:00", 120))
        data = self._read(body)
        self.assertEqual(list(data["gluc"]), [40.0, 400.0, 120.0])

    def test_carbs_and_fast_acting_insulin_pair_into_a_meal(self):
        body = (egv(11, "2026-05-01T07:55:00", 110)
                + "12,2026-05-01T08:00:00,Carbs,,,,iPhone G7,,,45,,,,\n"
                + "13,2026-05-01T08:02:00,Insulin,Fast-Acting,,,iPhone G7,,4.5,,,,,\n"
                + egv(14, "2026-05-01T08:05:00", 130))
        data = self._read(body)
        self.assertEqual(len(data["meals"]), 1)
        meal = data["meals"][0]
        self.assertEqual(meal["cho"], 45.0)
        self.assertEqual(meal["bolus"], 4.5)

    def test_long_acting_insulin_is_not_a_meal_bolus(self):
        """On injections the long-acting dose replaces a basal rate — it says
        nothing about a single meal and must not be counted as one."""
        body = (egv(11, "2026-05-01T07:55:00", 110)
                + "12,2026-05-01T08:00:00,Carbs,,,,iPhone G7,,,45,,,,\n"
                + "13,2026-05-01T22:00:00,Insulin,Long-Acting,,,iPhone G7,,18,,,,,\n"
                + egv(14, "2026-05-01T08:05:00", 130))
        data = self._read(body)
        # Without a bolus the carb entry is not an analysable meal (same rule as
        # for Glooko); what matters is that the 18 U never turn up as one.
        doses = [m["bolus"] for m in data["meals"] + data["minors"]]
        self.assertNotIn(18.0, doses)
        self.assertEqual(sum(doses), 0.0)

    def test_unit_comes_from_the_column_name(self):
        body = egv(11, "2026-05-01T08:00:00", "6.7")
        self._read(body, unit="mmol/L")
        self.assertEqual(core.glucose_unit(), "mmol/L")
        core.set_glucose_unit("mg/dL")

    def test_export_without_basal_is_lite(self):
        data = self._read(egv(11, "2026-05-01T08:00:00", 120))
        self.assertIsNone(data["basal"])
        self.assertEqual(data["source"], "dexcom")

    def test_glucose_only_export_still_reads(self):
        """Carbs and insulin are optional: they only exist if logged in the app."""
        body = "".join(egv(10 + i, f"2026-05-01T08:{i * 5:02d}:00", 100 + i) for i in range(6))
        data = self._read(body)
        self.assertEqual(data["meals"], [])
        self.assertEqual(len(data["times"]), 6)

    def test_export_without_glucose_is_refused(self):
        with self.assertRaises(core.LoopCRError):
            self._read("12,2026-05-01T08:00:00,Carbs,,,,iPhone G7,,,45,,,,\n")


class TestIsoTimestamps(unittest.TestCase):
    """Clarity writes ISO with a T; the other exports do not."""

    def test_parses_the_clarity_format(self):
        self.assertEqual(core.parse_ts("2023-01-15T00:00:23"),
                         datetime(2023, 1, 15, 0, 0, 23))

    def test_still_parses_the_older_formats(self):
        self.assertEqual(core.parse_ts("29.07.2026 09:02"), datetime(2026, 7, 29, 9, 2))
        self.assertEqual(core.parse_ts("2026-07-29 09:02"), datetime(2026, 7, 29, 9, 2))


if __name__ == "__main__":
    unittest.main()


class TestDexcomUpload(unittest.TestCase):
    """The web form has to recognise a Clarity CSV, not just the CLI."""

    def setUp(self):
        import webapp   # noqa: PLC0415  (kept local: the CLI tests need no Flask)
        self.client = webapp.app.test_client()

    def _post(self, body):
        import io
        csv_bytes = (HEADER.format(unit="mg/dL") + "\n" + META + body).encode("utf-8-sig")
        return self.client.post(
            "/report", content_type="multipart/form-data",
            data={"export": (io.BytesIO(csv_bytes), "clarity.csv"), "lang": "de"})

    def test_clarity_csv_produces_a_report(self):
        body = "".join(egv(10 + i, f"2026-05-0{1 + i // 24}T{i % 24:02d}:00:00", 110 + i % 40)
                       for i in range(60))
        response = self._post(body)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Teil 1", response.get_data(as_text=True))

    def test_clarity_upload_stays_lite(self):
        """No basal in the file means the CR assessment must not appear."""
        body = "".join(egv(10 + i, f"2026-05-0{1 + i // 24}T{i % 24:02d}:00:00", 110 + i % 40)
                       for i in range(60))
        self.assertNotIn("Teil 2", self._post(body).get_data(as_text=True))
