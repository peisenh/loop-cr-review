#!/usr/bin/env bash
# Regenerate the screenshots in docs/ from the bundled example data, so the
# pictures in the README always show the current report rather than whatever
# the layout looked like months ago.
#
# Usage:  ./tools/make-screenshots.sh [export-dir]     (default: example-data)
#
# Produces  docs/screenshot.png       — the top of the report (README)
#           docs/screenshot_full.png  — the whole page
set -euo pipefail

cd "$(dirname "$0")/.."
EXPORT_DIR="${1:-example-data}"
OUT_DIR="docs"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Chromium and Chrome take the same flags; different distributions ship
# different names, so take whichever is there instead of hard-coding one.
BROWSER=""
for candidate in chromium chromium-browser google-chrome google-chrome-stable; do
  if command -v "$candidate" >/dev/null 2>&1; then BROWSER="$candidate"; break; fi
done
if [ -z "$BROWSER" ]; then
  echo "No chromium/google-chrome found. Install one of:" >&2
  echo "  chromium · chromium-browser · google-chrome · google-chrome-stable" >&2
  exit 1
fi
echo "==> Using $BROWSER"

echo "==> Generating report from $EXPORT_DIR"
python3 loop_cr_review.py "$EXPORT_DIR" -o "$WORK/report.html" >/dev/null

shoot() {  # shoot <output> <height>
  "$BROWSER" --headless --disable-gpu --hide-scrollbars \
    --screenshot="$1" --window-size="1024,$2" "$WORK/report.html" 2>/dev/null
  [ -s "$1" ] || { echo "Screenshot $1 stayed empty" >&2; exit 1; }
  echo "    $1  ($(du -h "$1" | cut -f1))"
}

mkdir -p "$OUT_DIR"
echo "==> Rendering"
shoot "$OUT_DIR/screenshot.png" 1800
shoot "$OUT_DIR/screenshot_full.png" 5500

echo "==> Done. Check them before committing — a report that grew past 5500 px"
echo "    is cut off in screenshot_full.png without any error."
