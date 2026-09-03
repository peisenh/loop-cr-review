"""Regression tests against the synthetic example-data export.

These pin the intentional demo pattern (breakfast too strong, lunch too weak,
dinner adequate) and basic export/ZIP invariants so heuristic or parser changes
do not silently flip the demo report.
"""
from __future__ import annotations

import os
import logging
import tempfile
import unittest
import zipfile
from datetime import date, datetime, timedelta
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

    def test_daily_overview_builds(self):
        """Daily panels: light by default; dark only when requested."""
        _html, ctx = core.generate_report(EXAMPLE, lang="de", daily=True)
        self.assertGreaterEqual(len(ctx["daily_days"]), 1)
        for day in ctx["daily_days"]:
            self.assertTrue(day["img"])
            self.assertFalse(day["img_dark"])
        _html, ctx = core.generate_report(EXAMPLE, lang="de", daily=True, dark_charts=True)
        for day in ctx["daily_days"]:
            self.assertTrue(day["img"])
            self.assertTrue(day["img_dark"])

    def test_dark_charts_optional_for_all(self):
        """AGP/slot/norm dark PNGs only with dark_charts (same flag as daily)."""
        _html, ctx = core.generate_report(EXAMPLE, lang="de", daily=False)
        self.assertTrue(ctx["agp_img"])
        self.assertFalse(ctx["agp_img_dark"])
        self.assertFalse(ctx["slot_img_dark"])
        self.assertFalse(ctx["slot_norm_img_dark"])
        _html, ctx = core.generate_report(EXAMPLE, lang="de", daily=False, dark_charts=True)
        self.assertTrue(ctx["agp_img_dark"])
        self.assertTrue(ctx["slot_img_dark"])
        self.assertTrue(ctx["slot_norm_img_dark"])

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


class TestCgmGap(unittest.TestCase):
    def test_cgm_gap_in_window_detects_hole(self):
        start = datetime(2026, 7, 1, 8, 0, 0)
        # samples every 5 min but a 40 min hole after start+10
        times = [start + timedelta(minutes=m) for m in (0, 5, 10, 50, 55, 60, 120, 180, 240)]
        self.assertTrue(core.cgm_gap_in_window(start, 240, times, max_gap_min=25))

    def test_cgm_gap_in_window_dense_ok(self):
        start = datetime(2026, 7, 1, 8, 0, 0)
        times = [start + timedelta(minutes=m) for m in range(0, 241, 5)]
        self.assertFalse(core.cgm_gap_in_window(start, 240, times, max_gap_min=25))

    def test_select_prefers_non_gap_when_enough(self):
        rows = (
            [{"contam": False, "cgm_gap": False, "x": i} for i in range(3)]
            + [{"contam": False, "cgm_gap": True, "x": 99}]
        )
        used, n_clean, only = core.select_slot_rows(rows)
        self.assertTrue(only)
        self.assertEqual(n_clean, 4)  # contam-free count
        self.assertEqual(len(used), 3)
        self.assertTrue(all(not r.get("cgm_gap") for r in used))

    def test_select_fallback_includes_gap_when_few(self):
        rows = [
            {"contam": False, "cgm_gap": True, "x": 1},
            {"contam": False, "cgm_gap": True, "x": 2},
        ]
        used, n_clean, only = core.select_slot_rows(rows)
        self.assertFalse(only)
        self.assertEqual(len(used), 2)


class TestRenderedValues(unittest.TestCase):
    """The report must contain formatted values, not repr() of objects.

    Regression: a stray decorator left over from a refactor turned `fmt_cr`
    into a context manager. Every carb ratio in the report then rendered as
    "<contextlib._GeneratorContextManager object at 0x…>" — and the whole
    suite stayed green, because nothing looked at what the cells contain.
    """

    @classmethod
    def setUpClass(cls):
        cls.html, cls.ctx = core.generate_report(str(EXAMPLE), lang="de")

    def test_no_python_object_repr_in_output(self):
        for pattern in (r"&lt;[\w.]+ object at 0x", r"&lt;function ", r"&lt;generator "):
            with self.subTest(pattern=pattern):
                self.assertNotRegex(self.html, pattern)

    def test_carb_ratios_are_formatted(self):
        """Every slot shows a ratio as 1:x.x (or the em dash for nan)."""
        for slot in self.ctx["slots"]:
            with self.subTest(slot=slot["label"]):
                for key in ("cr", "cre"):
                    self.assertRegex(slot[key], r"^(1:\d+\.\d|—)$")

    def test_numeric_cells_look_numeric(self):
        for slot in self.ctx["slots"]:
            with self.subTest(slot=slot["label"]):
                self.assertRegex(slot["exc"], r"^[+-]\d+\.\d\d$")
                self.assertRegex(slot["cho"], r"^\d+$")

class TestDayTitle(unittest.TestCase):
    """Panel titles of the daily charts.

    Regression: a blanket rename of the variables X/Y also hit the strftime
    format, turning "%Y" into "%ys" — every daily panel then read
    "01.07.26s" instead of "01.07.2026". The suite did not notice, because
    chart content is only ever checked for being non-empty.
    """

    def test_date_is_a_four_digit_year(self):
        core.setup_i18n("de")
        title = core._day_title(date(2026, 7, 1), {})
        self.assertIn("01.07.2026", title)
        self.assertRegex(title, r"^\w+, \d{2}\.\d{2}\.\d{4}$")

    def test_title_carries_tdd_when_known(self):
        core.setup_i18n("de")
        tdd = {date(2026, 7, 1): (16.6, 36.7, 20.1)}   # (bolus, total, basal)
        self.assertIn("36.7", core._day_title(date(2026, 7, 1), tdd))


class TestChartsAreSelfContained(unittest.TestCase):
    """Charts are SVG, and nothing in the app compiles any more.

    This replaces two tests that guarded matplotlib's font cache and its
    logging — settings that had to be made before importing it, and that a
    tidy-up once dropped by accident. Neither has anything to guard now, and
    what took their place is the reason they went: no matplotlib anywhere in
    what ships.
    """

    def test_the_report_carries_no_bitmap_charts(self):
        html, _ctx = core.generate_report(EXAMPLE, lang="de")
        self.assertNotIn("data:image/png", html)
        self.assertIn("<svg", html)

    def test_charts_do_not_import_matplotlib(self):
        source = (Path(__file__).resolve().parents[1] / "lcr" / "charts.py").read_text()
        self.assertNotIn("import matplotlib", source)

    def test_a_chart_carries_its_own_colours(self):
        """One file for both themes: the dark variant is a media query in it."""
        html, _ctx = core.generate_report(EXAMPLE, lang="de")
        self.assertIn("prefers-color-scheme:dark", html.replace(" ", ""))

