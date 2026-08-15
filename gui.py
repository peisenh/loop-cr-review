"""Desktop launcher for loop-cr-review.

Runs the Flask web front-end on a local port with a production WSGI server
(waitress) and shows it in a native window (pywebview). Same upload form and
reports as the web/CLI, but as a double-click desktop app: no browser tab, no
Docker, localhost only, single user. Health data never leaves the machine.

Runtime backends pywebview uses: WebView2 (Edge) on Windows, WebKitGTK on
Linux. See requirements-gui.txt for the system prerequisites.
"""
import socket
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
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.2):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def main():
    """Start the local server in a thread and open the desktop window."""
    port = _free_port()
    threading.Thread(target=serve, args=(port,), daemon=True).start()
    wait_until_up(port)
    webview.create_window(WINDOW_TITLE, f"http://127.0.0.1:{port}/",
                          width=780, height=920)
    webview.start(gui='qt')


if __name__ == "__main__":
    main()
