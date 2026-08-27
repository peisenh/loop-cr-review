"""Desktop launcher for loop-cr-review.

Runs the Flask web front-end on a local port with a production WSGI server
(waitress) and shows it in a native window (pywebview). Same upload form and
reports as the web/CLI, but as a double-click desktop app: no browser tab, no
Docker, localhost only, single user. Health data never leaves the machine.

GUI backends (auto-selected unless LOOP_CR_GUI overrides):

- Windows with PyQt6 present (bundled Qt build) → Qt WebEngine
- Windows without PyQt6 (slim build) → Edge WebView2
- Linux → Qt WebEngine (WebKitGTK was unreliable)

Override: LOOP_CR_GUI=qt|edgechromium
"""
import importlib.util
import os
import socket
import sys
import threading
import time

import waitress
import webview

from webapp import app

WINDOW_TITLE = "loop-cr-review"


def _free_port():
    """Return a free localhost TCP port for the local server."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def serve(port):
    """Serve the Flask app with waitress (blocking; run in a thread)."""
    waitress.serve(app, host="127.0.0.1", port=port, threads=4)


def wait_until_up(port, timeout=15.0):
    """Block until the local server accepts connections, or time out."""
    deadline = time.monotonic() + timeout
    while time.monotonic() <= deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.2):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def _gui_backend():
    """Pick pywebview GUI backend for this build/platform.

    Bundled Windows Qt builds ship PyQt6 → use Qt. Slim Windows builds do not
    → Edge WebView2. Linux always uses Qt. LOOP_CR_GUI=qt|edgechromium forces.
    """
    forced = os.environ.get("LOOP_CR_GUI", "").strip().lower()
    if forced in ("edge", "webview2", "edgechromium"):
        return "edgechromium"
    if forced == "qt":
        return "qt"
    if sys.platform == "win32":
        # Present only in the full Qt Windows build; probe without importing
        # (find_spec avoids paying PyQt6's import cost just to check presence).
        return "qt" if importlib.util.find_spec("PyQt6") else "edgechromium"
    return "qt"


def main():
    """Start the local server in a thread and open the desktop window."""
    port = _free_port()
    threading.Thread(target=serve, args=(port,), daemon=True).start()
    wait_until_up(port)
    # Off by default. Without this Qt WebEngine ignores Content-Disposition
    # and the Save link in the report frame does nothing.
    webview.settings['ALLOW_DOWNLOADS'] = True
    webview.create_window(WINDOW_TITLE, f"http://127.0.0.1:{port}/",
                          width=780, height=920)
    webview.start(gui=_gui_backend())


if __name__ == "__main__":
    main()
