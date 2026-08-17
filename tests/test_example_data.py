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

    def test_report_method_box_and_cr_columns(self):
        self.assertTrue(
            "How to read this report" in self.html
            or "So liest man diesen Report" in self.html
        )
        self.assertTrue(
            "CR (CHO/bolus)" in self.html or "CR (CHO/Bolus)" in self.html
        )
        self.assertTrue(
            "CR_eff (+loop)" in self.html or "CR_eff (+Loop)" in self.html
        )
        self.assertTrue(
            "modulated basal" in self.html or "moduliertes Basal" in self.html
        )

        self.assertTrue(
            "all meals" in self.html or "alle Mahlzeiten" in self.html
        )
        # low-confidence legend present (wording de/en)
        self.assertTrue(
            "Hatched row" in self.html or "Schraffierte Zeile" in self.html
            or "low confidence" in self.html or "unsichere Datenlage" in self.html
        )
        self.assertIn("Boost / Ease-off", self.html)

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
        before = [s[0] for s in core.DEFAULT_SLOTS]
        custom = core.build_slots([
            {"key": "brunch", "label": "Brunch", "start": 9, "end": 12},
            {"key": "other", "label": "Other", "start": -1, "end": -1},
        ])
        core.generate_report(EXAMPLE, lang="de", slots=custom)
        # After the call, this context should still see default keys
        self.assertEqual([s[0] for s in core._slot_state()[0]], before)
        self.assertIn("breakfast", core._slot_state()[1])


class TestSelectSlotRows(unittest.TestCase):
    def test_prefers_clean_when_enough(self):
        rows = [{"contam": False, "x": i} for i in range(3)] + [{"contam": True, "x": 99}]
        used, n_clean, only = core.select_slot_rows(rows)
        self.assertTrue(only)
        self.assertEqual(n_clean, 3)
        self.assertEqual(len(used), 3)
        self.assertTrue(all(not r["contam"] for r in used))

    def test_fallback_when_few_clean(self):
        rows = [{"contam": False, "x": 1}, {"contam": True, "x": 2}]
        used, n_clean, only = core.select_slot_rows(rows)
        self.assertFalse(only)
        self.assertEqual(n_clean, 1)
        self.assertEqual(len(used), 2)


class TestContextIsolation(unittest.TestCase):
    """Language and glucose unit must not leak across concurrent callers."""

    def test_concurrent_lang_and_unit_isolated(self):
        import concurrent.futures
        import loop_cr_review as core

        def de_report():
            html, ctx = core.generate_report(EXAMPLE, lang="de")
            return "Frühstück" in html, ctx.get("unit")

        def en_report():
            html, ctx = core.generate_report(EXAMPLE, lang="en")
            return "Breakfast" in html, ctx.get("unit")

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f_de = pool.submit(de_report)
            f_en = pool.submit(en_report)
            de_ok, de_unit = f_de.result()
            en_ok, en_unit = f_en.result()
        self.assertTrue(de_ok)
        self.assertTrue(en_ok)
        # both example exports are mg/dL; units must still be consistent per call
        self.assertEqual(de_unit, en_unit)
