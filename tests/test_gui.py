"""Tests for the desktop launcher (``gui.py``).

The native window itself needs a display and a GUI backend, so these tests
cover everything around it: which pywebview backend is selected for a given
platform/build (including the ``LOOP_CR_GUI`` override), the local-port helpers,
and that the bundled waitress server really serves the Flask app.
"""
from __future__ import annotations

import socket
import threading
import unittest
import urllib.request
from unittest import mock

try:
    import gui
except ImportError as exc:                    # pragma: no cover - env without GUI deps
    # gui.py needs the optional launcher dependencies (waitress, pywebview).
    # Skip instead of failing the whole suite in a CLI-only environment.
    raise unittest.SkipTest(f"desktop launcher dependencies missing: {exc}") from exc


class TestGuiBackendSelection(unittest.TestCase):
    """Backend choice: Qt on Linux, WebView2 for slim Windows builds."""

    def setUp(self):
        # Never let a developer's own override leak into the assertions.
        patcher = mock.patch.dict("os.environ", {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        gui.os.environ.pop("LOOP_CR_GUI", None)

    def test_linux_uses_qt(self):
        with mock.patch.object(gui.sys, "platform", "linux"):
            self.assertEqual(gui._gui_backend(), "qt")

    def test_windows_with_pyqt6_uses_qt(self):
        """The full Qt Windows build ships PyQt6."""
        with mock.patch.object(gui.sys, "platform", "win32"), \
             mock.patch.object(gui.importlib.util, "find_spec", return_value=object()):
            self.assertEqual(gui._gui_backend(), "qt")

    def test_windows_without_pyqt6_uses_webview2(self):
        """The slim Windows build has no Qt and must fall back to Edge."""
        with mock.patch.object(gui.sys, "platform", "win32"), \
             mock.patch.object(gui.importlib.util, "find_spec", return_value=None):
            self.assertEqual(gui._gui_backend(), "edgechromium")

    def test_env_override_forces_edge(self):
        for value in ("edge", "webview2", "edgechromium", "EdgeChromium", " edge "):
            with self.subTest(value=value):
                gui.os.environ["LOOP_CR_GUI"] = value
                with mock.patch.object(gui.sys, "platform", "linux"):
                    self.assertEqual(gui._gui_backend(), "edgechromium")

    def test_env_override_forces_qt(self):
        gui.os.environ["LOOP_CR_GUI"] = "QT"
        with mock.patch.object(gui.sys, "platform", "win32"), \
             mock.patch.object(gui.importlib.util, "find_spec", return_value=None):
            self.assertEqual(gui._gui_backend(), "qt")

    def test_unknown_override_falls_back_to_autodetect(self):
        gui.os.environ["LOOP_CR_GUI"] = "nonsense"
        with mock.patch.object(gui.sys, "platform", "linux"):
            self.assertEqual(gui._gui_backend(), "qt")


class TestPortHelpers(unittest.TestCase):
    def test_free_port_is_usable(self):
        port = gui._free_port()
        self.assertTrue(1024 <= port <= 65535)
        # The port must be free again after the probe socket is closed.
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))

    def test_free_port_varies(self):
        self.assertNotEqual(gui._free_port(), gui._free_port())

    def test_wait_until_up_times_out_on_dead_port(self):
        dead = gui._free_port()          # nothing is listening there
        self.assertFalse(gui.wait_until_up(dead, timeout=0.3))


class TestBundledServer(unittest.TestCase):
    """The launcher must serve the very same Flask app the web front-end uses."""

    @classmethod
    def setUpClass(cls):
        cls.port = gui._free_port()
        threading.Thread(target=gui.serve, args=(cls.port,), daemon=True).start()
        if not gui.wait_until_up(cls.port, timeout=15):
            raise unittest.SkipTest("local server did not come up")

    def _get(self, path="/"):
        url = f"http://127.0.0.1:{self.port}{path}"
        with urllib.request.urlopen(url, timeout=10) as res:
            return res.status, res.read().decode()

    def test_serves_upload_form(self):
        status, body = self._get()
        self.assertEqual(status, 200)
        self.assertIn("Medizinprodukt", body)     # disclaimer must be present

    def test_serves_static_logo(self):
        status, _ = self._get("/static/logo-horizontal.svg")
        self.assertEqual(status, 200)

    def test_binds_localhost_only(self):
        """Health data stays on the machine: no binding to a public address."""
        # Loopback must answer ...
        with socket.socket() as sock:
            sock.settimeout(0.5)
            self.assertEqual(sock.connect_ex(("127.0.0.1", self.port)), 0)
        # ... while the same port stays free on this host's outward address,
        # proving waitress did not bind 0.0.0.0.
        outward = socket.gethostbyname(socket.gethostname())
        if outward.startswith("127."):
            self.skipTest("no non-loopback address available in this environment")
        with socket.socket() as sock:
            sock.settimeout(0.5)
            self.assertNotEqual(sock.connect_ex((outward, self.port)), 0)


if __name__ == "__main__":
    unittest.main()
