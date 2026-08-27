# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The entry point of the browser build.

It runs under Pyodide in the end, but it is ordinary Python: bytes in, report
out. Testing it here catches the parts that have nothing to do with the browser
- unpacking, finding the export, refusing what it cannot read.
"""
import io
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import loop_cr_review as core        # noqa: E402  pylint: disable=wrong-import-position
import browser_entry                 # noqa: E402  pylint: disable=wrong-import-position

EXAMPLE_ZIP = ROOT / "example-data" / "Alex_Beispiel_Glooko_export.zip"


class TestBuildReport(unittest.TestCase):
    def tearDown(self):
        import shutil   # noqa: PLC0415
        shutil.rmtree(browser_entry.WORK, ignore_errors=True)

    def test_a_glooko_zip_produces_a_report(self):
        html = browser_entry.build_report(EXAMPLE_ZIP.read_bytes(), "export.zip", lang="de")
        self.assertIn("Teil 1", html)
        self.assertGreater(len(html), 100_000)

    def test_the_unpacked_export_does_not_survive(self):
        """Health data has no reason to stay in the virtual filesystem."""
        browser_entry.build_report(EXAMPLE_ZIP.read_bytes(), "export.zip", lang="de")
        self.assertFalse(browser_entry.WORK.exists())

    def test_something_that_is_not_a_zip_says_so(self):
        with self.assertRaises(core.LoopCRError) as caught:
            browser_entry.build_report(b"\x01\x02\x03", "broken.zip")
        self.assertIn("ZIP", str(caught.exception))

    def test_an_archive_without_an_export_is_refused(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("notes.txt", "nothing to see")
        with self.assertRaises(core.LoopCRError) as caught:
            browser_entry.build_report(buf.getvalue(), "other.zip")
        self.assertIn("no Glooko", str(caught.exception))

    def test_a_path_escaping_the_archive_is_refused(self):
        """A crafted archive must not write outside the work directory."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("../escaped.csv", "x")
        with self.assertRaises(core.LoopCRError) as caught:
            browser_entry.build_report(buf.getvalue(), "evil.zip")
        self.assertIn("outside", str(caught.exception))

    def test_a_zip_bomb_is_refused(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("big.csv", b"0" * (browser_entry.MAX_TOTAL_BYTES + 1))
        with self.assertRaises(core.LoopCRError) as caught:
            browser_entry.build_report(buf.getvalue(), "bomb.zip")
        self.assertIn("300 MB", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
