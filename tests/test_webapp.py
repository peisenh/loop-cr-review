"""Tests for the Flask web front-end (``webapp.py``).

Covers the request boundary rather than the analysis itself: upload handling
and its hardening (zip-slip, decompression bombs, entry floods), the three slot
sources (built-in / field editor / uploaded JSON), option validation, the
download switch and reverse-proxy sub-path awareness.

Malformed input must always surface as a clean HTTP 400 — never a 500 with a
traceback, and never a worker crash.
"""
from __future__ import annotations

import io
import re
import unittest
import zipfile
from pathlib import Path

import webapp

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ZIP = ROOT / "example-data" / "Alex_Beispiel_Glooko_export.zip"


def _zip_bytes(members):
    """Build an in-memory ZIP from {name: bytes|str} for upload tests."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


class WebTestCase(unittest.TestCase):
    """Shared client plus a helper to POST an export to /report."""

    def setUp(self):
        self.client = webapp.app.test_client()
        self.example = EXAMPLE_ZIP.read_bytes()

    def post_report(self, zip_bytes=None, **fields):
        """POST a report request; defaults to the valid example export."""
        data = {"lang": "de", "window_hours": "4"}
        data.update(fields)
        data["export"] = (io.BytesIO(self.example if zip_bytes is None else zip_bytes),
                          "export.zip")
        return self.client.post("/report", data=data,
                                content_type="multipart/form-data")


class TestUploadForm(WebTestCase):
    def test_form_renders_with_disclaimer_and_repo(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        body = res.data.decode()
        self.assertIn("Medizinprodukt", body)      # disclaimer must be visible
        self.assertIn("github.com/peisenh", body)  # AGPL source link
        self.assertIn("/analyze", body)
        self.assertIn("/progress/JOB", body)

    def test_form_language_switch(self):
        self.assertEqual(self.client.get("/?lang=en").status_code, 200)
        self.assertEqual(self.client.get("/?lang=de").status_code, 200)
        # unknown language falls back instead of erroring
        self.assertEqual(self.client.get("/?lang=zz").status_code, 200)


class TestAsyncReport(WebTestCase):
    """Asynchronous report endpoint used by the browser and desktop GUI."""

    def test_async_report_reaches_done_and_result(self):
        res = self.client.post("/analyze", data={
            "lang": "de", "window_hours": "4",
            "export": (io.BytesIO(self.example), "export.zip"),
        }, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 200)
        job_id = res.get_json()["job_id"]
        self.assertRegex(job_id, r"^[0-9a-f]{32}$")

        # The job is intentionally asynchronous; poll the shared status file.
        import time
        deadline = time.time() + 15
        state = None
        while time.time() < deadline:
            status = self.client.get(f"/progress/{job_id}")
            self.assertEqual(status.status_code, 200)
            state = status.get_json()
            if state["state"] in ("done", "error"):
                break
            time.sleep(0.05)

        self.assertEqual(state["state"], "done", state)
        result = self.client.get(f"/result/{job_id}")
        self.assertEqual(result.status_code, 200)
        self.assertIn(b"<!doctype html>", result.data[:40].lower())

    def test_invalid_async_upload_is_rejected(self):
        res = self.client.post("/analyze", data={
            "lang": "de", "window_hours": "4",
            "export": (io.BytesIO(b"not a zip"), "export.zip"),
        }, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)


class TestReportHappyPath(WebTestCase):
    def test_default_slots_report(self):
        res = self.post_report()
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"<!doctype html>", res.data[:40].lower())

    def test_language_selects_report_language(self):
        de = self.post_report(lang="de").data.decode()
        en = self.post_report(lang="en").data.decode()
        self.assertIn("CR-Beurteilung", de)
        self.assertIn("CR Assessment", en)
        # html lang attribute follows the selected language
        self.assertEqual(re.search(r'<html lang="(\w+)"', de).group(1), "de")
        self.assertEqual(re.search(r'<html lang="(\w+)"', en).group(1), "en")

    def test_download_switch_sets_attachment_header(self):
        plain = self.post_report()
        self.assertNotIn("attachment", plain.headers.get("Content-Disposition", ""))
        download = self.post_report(download="on")
        self.assertIn("attachment", download.headers["Content-Disposition"])


class TestSlotSources(WebTestCase):
    def test_field_editor_slots_apply(self):
        res = self.post_report(slots_mode="fields",
                               slot_label=["Morgen", "Abend"],
                               slot_start=["6", "18"], slot_end=["10", "22"])
        self.assertEqual(res.status_code, 200)
        self.assertIn("Morgen", res.data.decode())

    def test_field_editor_catch_all_is_translated(self):
        """The auto-appended catch-all must use the localised label, not a literal."""
        res = self.post_report(lang="de", slots_mode="fields",
                               slot_label=["Morgen"], slot_start=["6"], slot_end=["10"])
        self.assertEqual(res.status_code, 200)
        self.assertIn("Sonstige", res.data.decode())

    def test_invalid_field_slots_give_400_not_500(self):
        """Regression: this path once caught only SystemExit and returned 500."""
        res = self.post_report(slots_mode="fields", slot_label=["X"],
                               slot_start=["10"], slot_end=["6"])
        self.assertEqual(res.status_code, 400)

    def test_non_numeric_field_slots_give_400(self):
        res = self.post_report(slots_mode="fields", slot_label=["X"],
                               slot_start=["morgens"], slot_end=["10"])
        self.assertEqual(res.status_code, 400)

    def test_uploaded_slots_json_applies(self):
        slots = (ROOT / "example-data" / "slots.example.json").read_bytes()
        data = {"lang": "de", "window_hours": "4", "slots_mode": "json",
                "export": (io.BytesIO(self.example), "export.zip"),
                "slots": (io.BytesIO(slots), "slots.json")}
        res = self.client.post("/report", data=data,
                               content_type="multipart/form-data")
        self.assertEqual(res.status_code, 200)

    def test_invalid_slots_json_gives_400(self):
        bad = b'[{"key":"a","label":"A","start":10,"end":6}]'
        data = {"lang": "de", "window_hours": "4", "slots_mode": "json",
                "export": (io.BytesIO(self.example), "export.zip"),
                "slots": (io.BytesIO(bad), "slots.json")}
        res = self.client.post("/report", data=data,
                               content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)


class TestOptionValidation(WebTestCase):
    def test_missing_export_gives_400(self):
        res = self.client.post("/report", data={"lang": "de"},
                               content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)

    def test_invalid_window_values_give_400(self):
        for bad in ("abc", "0", "99"):
            with self.subTest(window=bad):
                self.assertEqual(self.post_report(window_hours=bad).status_code, 400)

    def test_unknown_language_falls_back_to_german(self):
        """An unknown lang is not an error — it falls back to the default."""
        res = self.post_report(lang="zz")
        self.assertEqual(res.status_code, 200)
        self.assertIn("CR-Beurteilung", res.data.decode())


class TestUploadHardening(WebTestCase):
    """Malformed or hostile archives must be rejected with 400, never 500."""

    def test_not_a_zip(self):
        self.assertEqual(self.post_report(b"this is not a zip").status_code, 400)

    def test_zip_slip_path_traversal(self):
        self.assertEqual(self.post_report(_zip_bytes({"../evil.csv": "x"})).status_code, 400)

    def test_absolute_path_member(self):
        self.assertEqual(self.post_report(_zip_bytes({"/etc/evil.csv": "x"})).status_code, 400)

    def test_decompression_bomb(self):
        bomb = _zip_bytes({"cgm_data_1.csv": b"A" * (webapp.MAX_TOTAL_BYTES + 1024)})
        self.assertEqual(self.post_report(bomb).status_code, 400)

    def test_single_oversized_file(self):
        big = _zip_bytes({"cgm_data_1.csv": b"A" * (webapp.MAX_FILE_BYTES + 1024)})
        self.assertEqual(self.post_report(big).status_code, 400)

    def test_entry_flood(self):
        many = _zip_bytes({f"f{i}.csv": "x" for i in range(webapp.MAX_ENTRIES + 10)})
        self.assertEqual(self.post_report(many).status_code, 400)

    def test_zip_without_cgm_data(self):
        self.assertEqual(self.post_report(_zip_bytes({"readme.txt": "nothing"})).status_code, 400)

    def test_corrupt_csv_content(self):
        """Garbage inside an otherwise valid ZIP must not escape as a 500."""
        junk = _zip_bytes({"cgm_data_1.csv": "header\nheader\n" + "B" * 100_000})
        self.assertEqual(self.post_report(junk).status_code, 400)


class TestReverseProxyPrefix(WebTestCase):
    """Behind Traefik StripPrefix the app must build links with the prefix."""

    def test_links_without_prefix(self):
        body = self.client.get("/").data.decode()
        self.assertIn('action="/report"', body)

    def test_links_honour_forwarded_prefix(self):
        res = self.client.get("/", headers={"X-Forwarded-Prefix": "/loop-cr-review",
                                            "X-Forwarded-Proto": "https"})
        body = res.data.decode()
        self.assertIn('action="/loop-cr-review/report"', body)
        self.assertIn("/loop-cr-review/static/", body)

    def test_report_works_behind_prefix(self):
        data = {"lang": "de", "window_hours": "4",
                "export": (io.BytesIO(self.example), "export.zip")}
        res = self.client.post("/report", data=data,
                               content_type="multipart/form-data",
                               headers={"X-Forwarded-Prefix": "/loop-cr-review"})
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
