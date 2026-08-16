"""Regression tests against the synthetic example-data export.

These pin the intentional demo pattern (breakfast too strong, lunch too weak,
dinner adequate) and basic export/ZIP invariants so heuristic or parser changes
do not silently flip the demo report.
"""
from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

import loop_cr_review as core

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "example-data"
EXAMPLE_ZIP = EXAMPLE / "Alex_Beispiel_Glooko_export.zip"


class TestExampleDataLayout(unittest.TestCase):
    def test_folder_has_cgm_and_insulin(self):
        self.assertTrue(list(EXAMPLE.glob("cgm_data_*.csv")))
        insulin = EXAMPLE / "Insulin data"
        self.assertTrue(insulin.is_dir())
        self.assertTrue(list(insulin.glob("bolus_data_*.csv")))
        self.assertTrue(list(insulin.glob("basal_data_*.csv")))

    def test_glooko_zip_exists_and_extracts(self):
        self.assertTrue(EXAMPLE_ZIP.is_file(), "web-test ZIP missing")
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(EXAMPLE_ZIP) as zf:
                zf.extractall(tmp)
            root = Path(tmp)
            cgms = list(root.rglob("cgm_data_*.csv"))
            self.assertEqual(len(cgms), 1)
            parent = cgms[0].parent
            self.assertTrue((parent / "Insulin data").is_dir())
            self.assertTrue(list((parent / "Insulin data").glob("bolus_data_*.csv")))
            self.assertTrue(list((parent / "Insulin data").glob("basal_data_*.csv")))


class TestParsers(unittest.TestCase):
    def test_read_cgm_example(self):
        times, glucose, name, sensor = core.read_cgm(EXAMPLE)
        self.assertGreater(len(times), 1000)
        self.assertEqual(len(times), len(glucose))
        self.assertIn("Alex", name)
        self.assertTrue(sensor)

    def test_read_meals_example(self):
        meals, minors, pump = core.read_meals(EXAMPLE)
        self.assertGreaterEqual(len(meals), 30)
        self.assertTrue(pump)
        for m in meals:
            self.assertGreaterEqual(m["cho"], core.MEAL_MIN_CHO)
            self.assertGreater(m["bolus"], 0)


class TestSlotsFile(unittest.TestCase):
    def test_example_slots_json_loads(self):
        path = EXAMPLE / "slots.example.json"
        slots = core.load_slots_file(path)
        self.assertGreaterEqual(len(slots), 2)
        catchalls = [s for s in slots if s[2] == -1 and s[3] == -1]
        self.assertEqual(len(catchalls), 1)


class TestGenerateReportExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html, cls.ctx = core.generate_report(
            EXAMPLE, lang="de", window_hours=4.0, daily=False
        )

    def test_html_nonempty(self):
        self.assertIsInstance(self.html, str)
        self.assertGreater(len(self.html), 10_000)
        self.assertIn("Alex Beispiel", self.html)

    def test_meta(self):
        self.assertEqual(self.ctx["name"], "Alex Beispiel")
        self.assertEqual(self.ctx["days"], "14")
        self.assertEqual(self.ctx["unit"], "mg/dL")
        self.assertEqual(self.ctx["wlab"], "4h")
        self.assertIn("CamAPS", self.ctx["device"])

    def test_demo_slot_verdicts(self):
        """Synthetic data is built so breakfast is strong, lunch weak, dinner ok."""
        by_label = {s["label"]: s for s in self.ctx["slots"]}
        self.assertEqual(by_label["Frühstück"]["cls"], "strong")
        self.assertEqual(by_label["Mittag"]["cls"], "weak")
        self.assertEqual(by_label["Abend"]["cls"], "ok")
        for s in self.ctx["slots"]:
            self.assertGreaterEqual(s["n"], 10)
            self.assertGreaterEqual(s["clean"], 5)

    def test_meals_present(self):
        self.assertGreaterEqual(len(self.ctx["meals"]), 30)

    def test_english_report(self):
        html, ctx = core.generate_report(EXAMPLE, lang="en", window_hours=4.0)
        self.assertIn("Alex Beispiel", html)
        by_cls = {s["cls"] for s in ctx["slots"]}
        self.assertEqual(by_cls, {"strong", "weak", "ok"})


class TestGenerateReportFromZipExtract(unittest.TestCase):
    def test_report_from_extracted_zip_matches_folder_verdicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(EXAMPLE_ZIP) as zf:
                zf.extractall(tmp)
            root = Path(tmp)
            base = next(p.parent for p in root.rglob("cgm_data_*.csv"))
            _, ctx_zip = core.generate_report(base, lang="de", window_hours=4.0)
            _, ctx_dir = core.generate_report(EXAMPLE, lang="de", window_hours=4.0)
            z = {s["label"]: s["cls"] for s in ctx_zip["slots"]}
            d = {s["label"]: s["cls"] for s in ctx_dir["slots"]}
            self.assertEqual(z, d)


if __name__ == "__main__":
    unittest.main()


class TestLoopCRErrorAndSlotScope(unittest.TestCase):
    def test_invalid_slots_raise_not_sys_exit(self):
        with self.assertRaises(core.LoopCRError):
            core.build_slots([])
        with self.assertRaises(core.LoopCRError):
            core.build_slots([{"key": "a", "label": "A", "start": 0, "end": 8}])  # no catch-all

    def test_slot_scope_restores_defaults(self):
        before = list(core.SLOTS)
        custom = core.build_slots([
            {"key": "brunch", "label": "Brunch", "start": 9, "end": 12},
            {"key": "other", "label": "Other", "start": -1, "end": -1},
        ])
        core.generate_report(EXAMPLE, lang="de", slots=custom)
        self.assertEqual([s[0] for s in core.SLOTS], [s[0] for s in before])
        self.assertIn("breakfast", core.MAIN_SLOTS)
