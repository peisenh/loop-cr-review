# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Finding an export: bounded, and never guessing between several.

Both rules exist because of the same mistake — calling the tool without a
folder. It used to default to the working directory and search it recursively,
which on a home directory means walking everything and opening every CSV on the
way, then silently analysing whichever export sorted first.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import loop_cr_review as core   # noqa: E402  pylint: disable=wrong-import-position

CLARITY_HEAD = (
    "Index,Timestamp (YYYY-MM-DDThh:mm:ss),Event Type,Event Subtype,Patient Info,"
    "Device Info,Source Device ID,Glucose Value (mg/dL),Insulin Value (u),"
    "Carb Value (grams),Duration (hh:mm:ss),Glucose Rate of Change (mg/dL/min),"
    "Transmitter Time (Long Integer),Transmitter ID\n")
CLARITY_ROW = "11,2026-05-01T08:00:00,EGV,,,,iPhone,120,,,,,1,X\n"


class TestBoundedSearch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _csv(self, *parts):
        path = self.root.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(CLARITY_HEAD + CLARITY_ROW, encoding="utf-8-sig")
        return path

    def test_finds_files_in_the_folder_and_below(self):
        self._csv("here.csv")
        self._csv("sub", "one.csv")
        self._csv("sub", "deeper", "two.csv")
        names = {p.name for p in core.find_below(self.root, "*.csv")}
        self.assertEqual(names, {"here.csv", "one.csv", "two.csv"})

    def test_stops_below_the_depth_limit(self):
        """Three levels down is past any real export layout."""
        self._csv("a", "b", "c", "far.csv")
        names = {p.name for p in core.find_below(self.root, "*.csv")}
        self.assertNotIn("far.csv", names)

    def test_depth_is_configurable(self):
        self._csv("a", "b", "c", "far.csv")
        names = {p.name for p in core.find_below(self.root, "*.csv", depth=3)}
        self.assertIn("far.csv", names)


class TestRefusesToGuess(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _clarity(self, name):
        (self.root / name).write_text(CLARITY_HEAD + CLARITY_ROW, encoding="utf-8-sig")

    def test_one_export_is_used(self):
        self._clarity("export.csv")
        self.assertEqual(core.dexcom_csv(self.root).name, "export.csv")

    def test_two_exports_raise_instead_of_picking_one(self):
        self._clarity("a.csv")
        self._clarity("b.csv")
        with self.assertRaises(core.LoopCRError) as caught:
            core.dexcom_csv(self.root)
        # The message has to name the candidates, or the user cannot act on it.
        self.assertIn("a.csv", str(caught.exception))
        self.assertIn("b.csv", str(caught.exception))

    def test_no_export_is_not_an_error(self):
        self.assertIsNone(core.dexcom_csv(self.root))


class TestCliRequiresAFolder(unittest.TestCase):
    """Calling the tool without a folder must not start a search."""

    def test_missing_folder_is_a_usage_error(self):
        import subprocess   # noqa: PLC0415
        result = subprocess.run(
            [sys.executable, str(ROOT / "loop_cr_review.py")],
            capture_output=True, text=True, check=False, cwd=ROOT)
        self.assertEqual(result.returncode, 2)          # argparse usage error
        self.assertIn("export_dir", result.stderr)
        # It must not have produced a report from whatever lies in the repo.
        self.assertNotIn("written:", result.stdout)


if __name__ == "__main__":
    unittest.main()
