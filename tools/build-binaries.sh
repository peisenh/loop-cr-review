#!/usr/bin/env bash
# Build the PyInstaller binaries locally and smoke-test them, with the same
# flags the release workflow uses. For trying a build before tagging: a onefile
# binary can break in ways the test suite never sees (a bundled file that is not
# actually bundled, an import PyInstaller does not follow), and finding that out
# from a failed release is the expensive way.
#
# Usage:  ./tools/build-binaries.sh [cli|gui|webview2|all]   (default: cli)
#
# Leaves the result in dist/ and a generated report in build/smoke.html.
set -euo pipefail

cd "$(dirname "$0")/.."
TARGET="${1:-cli}"
SEP=":"; [[ "${OS:-}" == Windows_NT ]] && SEP=";"

# Everything runs through "python3 -m PyInstaller" on purpose: a pyinstaller on
# the PATH may belong to a different interpreter than the one whose packages get
# bundled. Inside a venv without pyinstaller installed, the system one takes over
# and quietly bundles the system packages — which is how a Qt GUI ends up without
# its WebEngine helper.
python3 -m PyInstaller --version >/dev/null 2>&1 || {
  echo "PyInstaller is not installed for $(command -v python3)." >&2
  echo "  pip install pyinstaller     — in the environment you build from" >&2
  exit 1; }

#echo "==> Compiling translation catalogs"
#pybabel compile -d locale >/dev/null

# The release workflow bakes the version in the same way; without it the report
# header would show the version of whatever _version.py happens to be around.
echo "==> Baking version"
cp -f _version.py build-version.bak 2>/dev/null || true
echo "VERSION = \"$(git describe --tags --always --dirty)\"" > _version.py

restore_version() {
  if [ -f build-version.bak ]; then mv -f build-version.bak _version.py
  else git checkout -- _version.py 2>/dev/null || true; fi
}
trap restore_version EXIT INT TERM

build_cli() {
  echo "==> Building CLI"
  python3 -m PyInstaller --onefile --name loop-cr-review \
    --add-data "templates/report.html.j2${SEP}templates" \
    --add-data "locale${SEP}locale" \
    loop_cr_review.py >/dev/null

  echo "==> Smoke test: report from example-data"
  mkdir -p build
  ./dist/loop-cr-review example-data -o build/smoke.html
  # A binary that starts but bundles no template still produces *something*, so
  # check the content, not the exit code.
  grep -q "CR" build/smoke.html || { echo "smoke.html has no report content" >&2; exit 1; }
  echo "    $(wc -c < build/smoke.html) bytes, $(du -h dist/loop-cr-review | cut -f1) binary"

  echo "==> Smoke test: English and a Nightscout-style run"
  ./dist/loop-cr-review example-data --lang en -o build/smoke-en.html >/dev/null
  echo "    ok"
}

build_gui() {   # Qt variant: the one built on every platform
  # --collect-all only warns when a package is missing and then builds happily,
  # so a machine without the qt extra produces a binary that dies on start with
  # "No module named 'qtpy'". Refuse before spending ten minutes on it.
  python3 - <<'PY' || { echo "  pip install -r requirements-gui.txt   (in a venv, not the system python)" >&2; exit 1; }
import importlib.util
import pathlib
import sys

missing = [m for m in ("qtpy", "PyQt6") if not importlib.util.find_spec(m)]
if missing:
    sys.exit(f"Qt GUI needs {', '.join(missing)} in the build environment.")

# The pip wheel carries the whole Qt runtime inside the package
# (PyQt6/Qt6/libexec/QtWebEngineProcess, resources, libs) and PyInstaller's hooks
# expect exactly that. Distribution packages split it across system paths, so
# --collect-all PyQt6 picks up the bindings without the WebEngine helper: the
# binary then aborts on start with "base::CommandLine cannot be properly
# initialized".
spec = importlib.util.find_spec("PyQt6")
root = pathlib.Path(spec.submodule_search_locations[0])
if not (root / "Qt6" / "libexec" / "QtWebEngineProcess").exists():
    sys.exit(f"PyQt6 at {root} has no bundled Qt runtime — this looks like a "
             "distribution package. Build from a venv with the pip wheels instead.")
PY
  echo "==> Building GUI (Qt)"
  python3 -m PyInstaller --onefile --windowed --name loop-cr-review-gui \
    --add-data "templates${SEP}templates" \
    --add-data "static${SEP}static" \
    --add-data "locale${SEP}locale" \
    --collect-all webview --collect-all PyQt6 --collect-all qtpy \
    gui.py >/dev/null
  check_gui dist/loop-cr-review-gui qt
}

build_gui_webview2() {   # slim Windows variant, no Qt bundled
  echo "==> Building GUI (WebView2 slim)"
  python3 -m PyInstaller --onefile --windowed --name loop-cr-review-gui-webview2 \
    --add-data "templates${SEP}templates" \
    --add-data "static${SEP}static" \
    --add-data "locale${SEP}locale" \
    --collect-all webview \
    gui.py >/dev/null
  check_gui dist/loop-cr-review-gui-webview2
}

check_gui() {  # check_gui <binary>
  # Starting it needs a display, so check what can be checked without one: that
  # the bundle really carries the templates and the catalogs. A GUI that opens
  # an empty window is the failure mode here. Read the archive rather than
  # grepping the binary — bundled files are compressed and would not be found.
  local bin="$1" flavour="${2:-}"
  python3 - "$bin" "$flavour" <<'PY'
import sys
from PyInstaller.archive.readers import CArchiveReader
entries = set(CArchiveReader(sys.argv[1]).toc)
missing = [n for n in ("templates/report.html.j2", "templates/upload.html.j2",
                       "locale/de/LC_MESSAGES/messages.mo",
                       "locale/en/LC_MESSAGES/messages.mo")
           if n not in entries]
if missing:
    sys.exit(f"{sys.argv[1]} does not bundle: {', '.join(missing)}")
# The data files being present says nothing about the GUI toolkit: a Qt build
# without qtpy starts and dies on the first window.
if sys.argv[2] == "qt" and not any(n.startswith(("qtpy", "PyQt6")) for n in entries):
    sys.exit(f"{sys.argv[1]} bundles no Qt: it would fail on start with a missing qtpy")
print(f"    bundle carries templates and catalogs ({len(entries)} entries)")
PY
  echo "    $(du -h "$bin" | cut -f1) binary (not started here: needs a display)"
}

case "$TARGET" in
  cli)       build_cli ;;
  gui)       build_gui ;;
  webview2)  build_gui_webview2 ;;
  all)       build_cli; build_gui
             # The slim variant is a Windows asset; building it elsewhere still
             # tells you whether the bundle is complete.
             build_gui_webview2 ;;
  *) echo "Usage: ./tools/build-binaries.sh [cli|gui|webview2|all]" >&2; exit 1 ;;
esac

echo "==> Done. Binaries in dist/, smoke report in build/smoke.html"
