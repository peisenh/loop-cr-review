"""Start the existing Flask web app on loopback for the Android WebView."""
import os
import tempfile
import threading
from pathlib import Path

# Writable cache before numpy/matplotlib import chains pull fonts
_cache = Path(tempfile.gettempdir()) / "loop-cr-review-android"
_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_cache / "mpl"))
os.environ.setdefault("XDG_CACHE_HOME", str(_cache))
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)

from werkzeug.serving import make_server

from webapp import app

_server = None
_thread = None


def start():
    """Bind Flask to 127.0.0.1 on an ephemeral port; return the port number."""
    global _server, _thread
    if _server is None:
        # templates/locale live next to this package tree under Chaquopy
        root = Path(__file__).resolve().parent
        app.template_folder = str(root / "templates")
        _server = make_server("127.0.0.1", 0, app, threaded=True)
        _thread = threading.Thread(
            target=_server.serve_forever, name="loop-cr-flask", daemon=True
        )
        _thread.start()
    return _server.server_port


def stop():
    global _server, _thread
    if _server is not None:
        _server.shutdown()
        _server.server_close()
        _server = None
        _thread = None
