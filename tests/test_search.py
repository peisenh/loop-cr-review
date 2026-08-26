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
import unittest.mock
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


class TestReadsNothingUnrelated(unittest.TestCase):
    """What the search is allowed to touch.

    The readers used to open every CSV below the given folder to look at its
    header — bank statements included, if one happened to lie there.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _noise(self):
        for rel in ("bank/statement.csv", "notes/passwords.csv", "photos/list.csv"):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("service;user;secret\n", encoding="utf-8")

    def test_a_glooko_export_reads_no_other_file(self):
        """Glooko is recognised by file name, so nothing else needs opening."""
        import builtins   # noqa: PLC0415
        import shutil     # noqa: PLC0415
        shutil.copytree(ROOT / "example-data", self.root / "Export", dirs_exist_ok=True)
        self._noise()
        opened, real_open = [], builtins.open

        def spy(file, *args, **kwargs):
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        builtins.open = spy
        try:
            core.generate_report(str(self.root / "Export"), lang="de")
        finally:
            builtins.open = real_open
        stray = [f for f in opened if any(part in f for part in ("bank", "notes", "photos"))]
        self.assertEqual(stray, [])

    def test_noise_directories_are_skipped(self):
        for rel in ("node_modules/a.csv", ".git/b.csv", "__pycache__/c.csv",
                    ".hidden/d.csv", "Export/wanted.csv"):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x\n", encoding="utf-8")
        names = [p.name for p in core.find_below(self.root, "*.csv")]
        self.assertEqual(names, ["wanted.csv"])

    def test_too_many_candidates_are_refused(self):
        """A folder full of spreadsheets is not an export folder."""
        for i in range(core.MAX_SNIFF_FILES + 5):
            (self.root / f"sheet_{i}.csv").write_text("a;b\n", encoding="utf-8")
        with self.assertRaises(core.LoopCRError) as caught:
            core.libreview_csv(self.root)
        self.assertIn("does not look like an export folder", str(caught.exception))

    def test_only_the_head_of_a_file_is_read(self):
        """A file without line breaks must not be read whole to sniff it."""
        big = "x" * (core.HEAD_BYTES * 20)
        (self.root / "huge.csv").write_text(big, encoding="utf-8")
        self.assertIsNone(core.libreview_csv(self.root))


class TestRealExportIsNotRefused(unittest.TestCase):
    """The cap must not fire on a real export.

    Regression: the limit was set to 12 while a Glooko export holds 18 CSVs
    (cgm, bolus, basal, alarms, ...). The web upload refused them, because it
    asked the content-sniffing readers before checking for Glooko's file names.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_cap_sits_above_a_glooko_export(self):
        self.assertGreaterEqual(core.MAX_SNIFF_FILES, 20)

    def test_eighteen_csvs_are_still_sniffed(self):
        for name in ("cgm_data_1", "cgm_data_2", "cgm_data_3", "bolus_data_1",
                     "basal_data_1", "bg_data_1", "alarms_data_1", "cgm_carbs_data_1",
                     "insulin_data_1", "pump_data_1", "notes_data_1", "exercise_data_1",
                     "carbs_data_1", "device_data_1", "settings_data_1", "food_data_1",
                     "reminders_data_1", "summary_data_1"):
            (self.root / f"{name}.csv").write_text("a;b\n1;2\n", encoding="utf-8")
        self.assertEqual(len(core.sniff_candidates(self.root, "*.csv", "CSV files")), 18)

    def test_web_upload_checks_glooko_before_reading_headers(self):
        """A folder with cgm_data_*.csv is a Glooko export - no sniffing needed."""
        import webapp   # noqa: PLC0415
        (self.root / "cgm_data_1.csv").write_text("x\n", encoding="utf-8")
        (self.root / "Insulin data").mkdir()
        with unittest.mock.patch("webapp.libreview_csv") as sniffed:
            base = webapp._find_export_base(str(self.root))
        sniffed.assert_not_called()
        self.assertEqual(Path(base), self.root)
