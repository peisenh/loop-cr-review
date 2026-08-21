import tempfile
import unittest
from pathlib import Path

import loop_cr_review as core


def _row(typ, ts, extra):
    cells = [""] * 21
    cells[0] = "FreeStyle Libre 3"
    cells[1] = "abc"
    cells[2] = ts
    cells[3] = typ
    for k, v in extra.items():
        cells[k] = v
    return ",".join(cells)


HEADER = (
    "Gerät,Seriennummer,Gerätezeitstempel,Aufzeichnungstyp,"
    "Glukosewert-Verlauf mg/dL,Glukose-Scan mg/dL,"
    "Nicht numerisches schnellwirkendes Insulin,Schnellwirkendes Insulin (Einheiten),"
    "Nicht numerische Nahrungsdaten,Kohlenhydrate (Gramm),Kohlenhydrate (Portionen),"
    "Nicht numerisches Depotinsulin,Depotinsulin (Einheiten),Notizen,"
    "Glukose-Teststreifen mg/dL,Keton mmol/L,Mahlzeiteninsulin (Einheiten),"
    "Korrekturinsulin (Einheiten),Insulin-Änderung durch Anwender (Einheiten),"
    "Zurückliegender Ketonwert mmol/L,Scan-Ketonwert mmol/L"
)


class TestLibreView(unittest.TestCase):
    def test_reads_and_stays_lite(self):
        body = "\n".join([
            "Glukose-Werte,Erstellt am,21-08-2026 16:24 UTC,Erstellt von,Example",
            HEADER,
            _row("0", "21-08-2026 10:00", {4: "110"}),
            _row("0", "21-08-2026 10:05", {4: "118"}),
            _row("5", "21-08-2026 10:00", {9: "50"}),
            _row("4", "21-08-2026 10:01", {7: "5.0"}),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "export.csv").write_text(body, encoding="utf-8")
            data = core.read_libreview(tmp)
            self.assertEqual(len(data["times"]), 2)
            self.assertEqual(len(data["meals"]), 1)
            self.assertAlmostEqual(data["meals"][0]["cho"], 50)
            self.assertAlmostEqual(data["meals"][0]["bolus"], 5)
            html, ctx = core.generate_report(tmp, lang="en")
            self.assertEqual(ctx["source"], "libreview")
            self.assertTrue(ctx["lite"])
            self.assertEqual(ctx["slots"], [])
            self.assertNotIn("How to read this report (CamAPS", html)
            self.assertIn("LibreView", html)
            self.assertIn("Per-meal", html)
            self.assertEqual(core.glucose_unit(), "mg/dL")
            html_d, ctx_d = core.generate_report(tmp, lang="en", daily=True)
            self.assertTrue(ctx_d["daily_days"])

    def test_span_and_clip(self):
        body = "\n".join([
            "Glukose-Werte,Erstellt am,21-08-2026 16:24 UTC,Erstellt von,Example",
            HEADER,
            _row("0", "20-08-2026 10:00", {4: "110"}),
            _row("0", "21-08-2026 10:00", {4: "118"}),
            _row("5", "21-08-2026 10:00", {9: "50"}),
            _row("4", "21-08-2026 10:01", {7: "5.0"}),
        ])
        import tempfile
        from pathlib import Path as P
        from datetime import date
        with tempfile.TemporaryDirectory() as tmp:
            P(tmp, "export.csv").write_text(body, encoding="utf-8")
            info = core.peek_span(tmp)
            self.assertEqual(info["from"], "2026-08-20")
            self.assertEqual(info["to"], "2026-08-21")
            self.assertEqual(info["days"], 2)
            _html, ctx = core.generate_report(tmp, lang="en",
                date_from=date(2026, 8, 21), date_to=date(2026, 8, 21))
            self.assertTrue(ctx["span"].startswith("21.08.2026"))
