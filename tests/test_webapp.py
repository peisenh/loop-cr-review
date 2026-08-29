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
import json
import os
import shutil
import threading
import time
import unittest
import unittest.mock
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
        page = result.data.decode()
        self.assertIn("<iframe", page)
        self.assertIn(f"/result/{job_id}/body", page)
        body = self.client.get(f"/result/{job_id}/body")
        self.assertEqual(body.status_code, 200)
        self.assertIn(b"<!doctype html>", body.data[:40].lower())
        # Looking at the chrome must not delete the job: Save still works.
        saved = self.client.get(f"/result/{job_id}/download")
        self.assertEqual(saved.status_code, 200)
        self.assertIn("attachment", saved.headers.get("Content-Disposition", ""))
        self.assertIn(b"<!doctype html>", saved.data[:40].lower())

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


class TestJobCleanup(unittest.TestCase):
    """Nothing may be left behind when the browser walks away.

    Cleanup used to happen only when the client fetched the result or polled
    after the TTL. A tab closed right after the upload left the export, the
    unpacked files and the finished report in the temp area for as long as the
    machine ran — health data with no expiry.
    """

    def setUp(self):
        self.root = webapp._JOB_ROOT
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.root, True)

    def _stale_job(self, age_seconds):
        job = self.root / ("a" * 32)
        job.mkdir()
        (job / "result.html").write_text("<html></html>", encoding="utf-8")
        stamp = time.time() - age_seconds
        os.utime(job, (stamp, stamp))
        return job

    def test_a_job_past_the_ttl_is_removed(self):
        job = self._stale_job(webapp.JOB_TTL + 60)
        webapp._sweep_stale_jobs()
        self.assertFalse(job.exists())

    def test_a_fresh_job_survives(self):
        """The sweep runs on every new upload and must not hit running jobs."""
        job = self._stale_job(5)
        webapp._sweep_stale_jobs()
        self.assertTrue(job.exists())

    def test_a_new_upload_sweeps_first(self):
        stale = self._stale_job(webapp.JOB_TTL + 60)
        client = webapp.app.test_client()
        with open(EXAMPLE_ZIP, "rb") as handle:
            client.post("/analyze", content_type="multipart/form-data",
                        data={"export": (io.BytesIO(handle.read()), "e.zip"), "lang": "de"})
        self.assertFalse(stale.exists())

    def test_sweep_survives_a_file_in_the_job_root(self):
        (self.root / "stray.txt").write_text("x", encoding="utf-8")
        webapp._sweep_stale_jobs()          # must not raise


class TestJobRootIsOurs(unittest.TestCase):
    """The temp area is shared, so the job directory has to be checked.

    Creating it with mode 0o700 only helps when we are the ones creating it.
    An existing directory keeps whatever owner and mode it has — someone could
    put it there first and read the exports afterwards.
    """

    def setUp(self):
        self.root = webapp._JOB_ROOT
        shutil.rmtree(self.root, ignore_errors=True)
        self.addCleanup(webapp._prepare_job_root)
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_a_fresh_directory_is_private(self):
        webapp._prepare_job_root()
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)

    def test_permissions_that_are_too_open_are_tightened(self):
        self.root.mkdir(mode=0o777)
        webapp._prepare_job_root()
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)

    def test_a_file_in_the_way_is_refused(self):
        self.root.write_text("not a directory", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            webapp._prepare_job_root()
        self.root.unlink()

    @unittest.skipUnless(os.getuid() == 0, "changing the owner needs root")
    def test_a_directory_owned_by_someone_else_is_refused(self):
        self.root.mkdir(mode=0o700)
        os.chown(self.root, 12345, 12345)
        try:
            with self.assertRaises(RuntimeError):
                webapp._prepare_job_root()
        finally:
            os.chown(self.root, os.getuid(), os.getgid())


class TestConcurrencyLimit(unittest.TestCase):
    """An unbounded thread per upload is an easy way to exhaust a home server."""

    def test_only_a_few_analyses_run_at_once(self):
        self.assertGreaterEqual(webapp.MAX_CONCURRENT_JOBS, 1)
        self.assertLessEqual(webapp.MAX_CONCURRENT_JOBS, 4)

    def test_further_jobs_wait_instead_of_starting(self):
        """The semaphore hands out exactly MAX_CONCURRENT_JOBS slots."""
        held = [webapp._JOB_SLOTS.acquire(blocking=False)
                for _ in range(webapp.MAX_CONCURRENT_JOBS)]
        try:
            self.assertTrue(all(held))
            self.assertFalse(webapp._JOB_SLOTS.acquire(blocking=False))
        finally:
            for _ in [h for h in held if h]:
                webapp._JOB_SLOTS.release()


class TestStaleDateRange(unittest.TestCase):
    """Choosing a second file must not keep the first file's date range.

    Going back in the browser restores the form, including a range that was read
    from the export chosen before. Picking another file then produced a report
    request for a period the new export may not even cover.
    """

    def setUp(self):
        self.html = webapp.app.test_client().get("/").get_data(as_text=True)

    def test_the_range_is_cleared_before_the_new_one_is_fetched(self):
        self.assertIn("clearRange", self.html)

    def test_going_back_clears_the_restored_range(self):
        self.assertIn("pageshow", self.html)

    def test_submitting_is_blocked_while_the_range_is_unknown(self):
        self.assertIn("submitBtn.disabled = true", self.html)


class TestErrorMessagesReachTheUser(unittest.TestCase):
    """A job failure has to say what went wrong."""

    def setUp(self):
        shutil.rmtree(webapp._JOB_ROOT, ignore_errors=True)
        webapp._prepare_job_root()
        self.addCleanup(shutil.rmtree, webapp._JOB_ROOT, True)

    def test_a_range_outside_the_data_says_so(self):
        client = webapp.app.test_client()
        with open(EXAMPLE_ZIP, "rb") as handle:
            job_id = client.post(
                "/analyze", content_type="multipart/form-data",
                data={"export": (io.BytesIO(handle.read()), "e.zip"), "lang": "de",
                      "date_from": "2026-01-01", "date_to": "2026-01-14"}
            ).get_json()["job_id"]
        for _ in range(120):
            time.sleep(0.5)
            state = client.get(f"/progress/{job_id}").get_json()
            if state and state.get("state") in ("done", "error"):
                break
        self.assertEqual(state.get("state"), "error")
        # The generic line alone would leave the user guessing.
        self.assertIn("date range", state.get("error", ""))


class TestFormRecoversAfterDownload(unittest.TestCase):
    """With "download" ticked the browser saves the file and stays on the page.

    Nothing navigated away, so nothing reset the form: the box kept announcing a
    running analysis and the button stayed disabled — no second report without a
    reload.
    """

    def setUp(self):
        self.html = webapp.app.test_client().get("/").get_data(as_text=True)

    def test_the_button_is_re_enabled_after_the_result_is_requested(self):
        after = self.html.split("window.location.href", 1)[1][:600]
        self.assertIn("submitBtn.disabled = false", after)

    def test_the_progress_box_ends_on_done(self):
        after = self.html.split("window.location.href", 1)[1][:600]
        self.assertIn('stage: "done"', after)


class TestResultRoutesWhileRunning(unittest.TestCase):
    """A report that is not finished yet must say so, not fail.

    Regression: the helper signalled "not ready" by returning a 2-tuple, while
    the callers told a result apart from a response by asking whether it was a
    tuple — so they unpacked the 409 into three names and every route answered
    500 while an analysis was still running.
    """

    def setUp(self):
        shutil.rmtree(webapp._JOB_ROOT, ignore_errors=True)
        webapp._prepare_job_root()
        self.addCleanup(shutil.rmtree, webapp._JOB_ROOT, True)
        self.job_id = "b" * 32
        (webapp._JOB_ROOT / self.job_id).mkdir(parents=True)
        job, status_path, _result = webapp._job_paths(self.job_id)
        status_path.write_text(json.dumps({"state": "running", "percent": 30}),
                               encoding="utf-8")
        self.client = webapp.app.test_client()

    def test_all_three_routes_answer_409(self):
        for path in (f"/result/{self.job_id}",
                     f"/result/{self.job_id}/body",
                     f"/result/{self.job_id}/external",
                     f"/result/{self.job_id}/print",
                     f"/result/{self.job_id}/download"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 409)

    def test_an_unknown_job_is_a_404(self):
        self.assertEqual(self.client.get("/result/" + "c" * 32).status_code, 404)


class TestViewingKeepsTheJob(unittest.TestCase):
    """Looking at a report must not delete it — Save comes after looking."""

    def setUp(self):
        shutil.rmtree(webapp._JOB_ROOT, ignore_errors=True)
        webapp._prepare_job_root()
        self.addCleanup(shutil.rmtree, webapp._JOB_ROOT, True)
        self.job_id = "d" * 32
        (webapp._JOB_ROOT / self.job_id).mkdir(parents=True)
        self.job, status_path, result_path = webapp._job_paths(self.job_id)
        status_path.write_text(json.dumps({"state": "done", "lang": "de"}),
                               encoding="utf-8")
        result_path.write_text("<html><body>report</body></html>", encoding="utf-8")
        self.client = webapp.app.test_client()

    def test_the_viewer_leaves_the_job_in_place(self):
        self.assertEqual(self.client.get(f"/result/{self.job_id}").status_code, 200)
        self.assertTrue(self.job.exists())

    def test_the_frame_serves_the_report_unchanged(self):
        body = self.client.get(f"/result/{self.job_id}/body").get_data(as_text=True)
        self.assertEqual(body, "<html><body>report</body></html>")

    def test_saving_hands_over_a_file_and_keeps_the_job(self):
        """A second Save has to work too; the TTL sweep does the cleaning."""
        response = self.client.get(f"/result/{self.job_id}/download")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers.get("Content-Disposition", ""))
        self.assertTrue(self.job.exists())


class TestRawInputGoesEarly(unittest.TestCase):
    """The export must not outlive the report it produced.

    Viewing a report deliberately keeps the job alive, so Save and a second look
    work. That would also have kept the uploaded ZIP and the unpacked CSVs lying
    around until the TTL sweep — the actual health data, long after anything
    needed it.
    """

    def setUp(self):
        shutil.rmtree(webapp._JOB_ROOT, ignore_errors=True)
        webapp._prepare_job_root()
        self.addCleanup(shutil.rmtree, webapp._JOB_ROOT, True)
        self.client = webapp.app.test_client()

    def test_only_report_and_status_remain(self):
        with open(EXAMPLE_ZIP, "rb") as handle:
            job_id = self.client.post(
                "/analyze", content_type="multipart/form-data",
                data={"export": (io.BytesIO(handle.read()), "e.zip"), "lang": "de"}
            ).get_json()["job_id"]
        for _ in range(120):
            time.sleep(0.5)
            state = self.client.get(f"/progress/{job_id}").get_json()
            if state and state.get("state") in ("done", "error"):
                break
        self.assertEqual(state.get("state"), "done")
        job = webapp._JOB_ROOT / job_id
        self.assertEqual(sorted(p.name for p in job.iterdir()),
                         ["result.html", "status.json"])
        # And the report is still there to look at.
        self.assertEqual(self.client.get(f"/result/{job_id}/body").status_code, 200)

    def test_drop_raw_input_keeps_what_it_is_told_to(self):
        job = webapp._JOB_ROOT / ("f" * 32)
        (job / "export").mkdir(parents=True)
        (job / "export" / "cgm_data_1.csv").write_text("x", encoding="utf-8")
        (job / "upload.zip").write_text("x", encoding="utf-8")
        (job / "status.json").write_text("{}", encoding="utf-8")
        (job / "result.html").write_text("<html></html>", encoding="utf-8")
        webapp._drop_raw_input(job, keep={"status.json", "result.html"})
        self.assertEqual(sorted(p.name for p in job.iterdir()),
                         ["result.html", "status.json"])


class TestSweepRunsOnATimer(unittest.TestCase):
    """The TTL has to bite on a machine that is simply left running."""

    def test_a_sweeper_thread_is_started(self):
        names = [t.name for t in threading.enumerate()]
        running = any(getattr(t, "_target", None) is webapp._sweep_forever
                      for t in threading.enumerate())
        self.assertTrue(running, f"no sweeper among {names}")

    def test_the_sweeper_survives_a_failing_sweep(self):
        """One bad sweep must not end the thread and stop all later ones."""
        with unittest.mock.patch("webapp._sweep_stale_jobs", side_effect=OSError):
            with unittest.mock.patch("webapp.time.sleep",
                                     side_effect=[None, StopIteration]):
                with self.assertRaises(StopIteration):
                    webapp._sweep_forever(interval=0)
