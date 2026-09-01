#!/usr/bin/env bash
# Regenerate the Play Store screenshots from the bundled example data.
#
# Taking them by hand on a phone means redoing every one of them whenever a
# heading or a wording changes. They show HTML — the upload form and the report
# in the app's chrome — so a headless browser at phone size produces the same
# pictures, in both store languages, in one command.
#
# Usage:  ./tools/make-play-screenshots.sh [export-dir]   (default: example-data)
#
# Produces  docs/play/<lang>/00-upload.png     the form
#           docs/play/<lang>/01-…  02-…  03-…  sections of the report
set -euo pipefail

cd "$(dirname "$0")/.."
EXPORT_DIR="${1:-example-data}"
OUT_ROOT="docs/play"
WORK="$(mktemp -d)"
SERVER_PID=""
cleanup() {
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

# Same viewport as tools/make-play-shots.py, so the upload shot and the report
# shots come out the same size: 412x915 CSS at 2.62x is 1080x2400, what a Pixel 8
# itself produces.
VIEWPORT="412,915"
SCALE=2.6214

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

shoot() {  # shoot <url-or-file> <output>
  "$BROWSER" --headless --disable-gpu --hide-scrollbars \
    --force-device-scale-factor="$SCALE" --window-size="$VIEWPORT" \
    --virtual-time-budget=4000 --screenshot="$2" "$1" 2>/dev/null
  [ -s "$2" ] || { echo "Screenshot $2 stayed empty" >&2; exit 1; }
  # The browser writes PNGs with an alpha channel and the store rejects those,
  # with no hint about why. Flatten first, then check the rest of the rules.
  python3 tools/check-play-shot.py "$2"
}

# The upload form is served, not a file: it pulls its logo and stylesheet from
# /static, which a file:// page cannot reach.
PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
python3 -c "
import webapp
webapp.app.run(host='127.0.0.1', port=$PORT, threaded=True)
" >/dev/null 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 40); do
  if python3 -c "
import socket, sys
try:
    socket.create_connection(('127.0.0.1', $PORT), 0.2).close()
except OSError:
    sys.exit(1)
" 2>/dev/null; then break; fi
  sleep 0.25
done

# Which sections to photograph, by the heading each one starts with. Spaced far
# enough apart that the pictures do not repeat each other: a phone screen holds
# two or three cards, so neighbouring sections show largely the same thing. AGP
# is not listed separately for that reason — it is already in the first shot.
sections_de=(
  "01-kennzahlen:Time in Ranges"
  "02-mahlzeiten:Reale Postprandial-Verläufe"
  "03-beurteilung:CR-Beurteilung pro Slot"
)
sections_en=(
  "01-key-figures:Time in Ranges"
  "02-meals:Real postprandial"
  "03-assessment:CR assessment per slot"
)

for lang in de en; do
  OUT="$OUT_ROOT/$lang"
  mkdir -p "$OUT"
  echo "==> $lang"

  shoot "http://127.0.0.1:$PORT/?lang=$lang" "$OUT/00-upload.png"

  python3 loop_cr_review.py "$EXPORT_DIR" --lang "$lang" -o "$WORK/report-$lang.html" >/dev/null
  if [ "$lang" = "de" ]; then sections=("${sections_de[@]}"); else sections=("${sections_en[@]}"); fi
  python3 tools/make-play-shots.py "$WORK/report-$lang.html" "$OUT" "${sections[@]}"
  python3 tools/check-play-shot.py "$OUT"/*.png
done

echo "==> Done"
echo "    Look at them before uploading. A section that runs past the screen is"
echo "    cut where a phone would cut it, which is usually right but not always."
