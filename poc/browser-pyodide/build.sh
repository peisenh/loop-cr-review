#!/usr/bin/env bash
# Assemble the offline browser build: one folder with index.html, the Pyodide
# runtime and the analysis code. Open index.html from disk and everything runs
# in the tab - no server, no upload, no network access after loading.
#
# Usage:  ./poc/browser-pyodide/build.sh [pyodide-version]
#
# Result:  dist/web/            the unpacked build (open dist/web/index.html)
#          dist/loop-cr-review-browser-poc.zip
set -euo pipefail

cd "$(dirname "$0")/../.."   # repository root
PYODIDE_VERSION="${1:-314.0.6}"
OUT="dist/browser-pyodide"
CACHE="build/pyodide-$PYODIDE_VERSION"

# Only the packages the analysis actually imports, plus what they pull in.
# Shipping all 300 wheels would multiply the download for no gain.
WHEELS=(numpy matplotlib jinja2 markupsafe pillow contourpy cycler fonttools
        kiwisolver packaging pyparsing python_dateutil pytz six)

echo "==> Fetching Pyodide $PYODIDE_VERSION"
mkdir -p build "$OUT"
if [ ! -d "$CACHE" ]; then
  url="https://github.com/pyodide/pyodide/releases/download/$PYODIDE_VERSION/pyodide-$PYODIDE_VERSION.tar.bz2"
  curl -fL --progress-bar -o "build/pyodide.tar.bz2" "$url"
  tar xf build/pyodide.tar.bz2 -C build
  mv build/pyodide "$CACHE"
  rm -f build/pyodide.tar.bz2
fi

echo "==> Copying the runtime"
rm -rf "$OUT"; mkdir -p "$OUT/pyodide"
# Every one of these is required at runtime. Copying "if present" once produced a
# build that loaded halfway and then died on a missing pyodide.asm.mjs, with the
# page stuck and nothing to go on - so a missing file has to stop the build.
REQUIRED=(pyodide.mjs pyodide.asm.mjs pyodide.asm.wasm python_stdlib.zip pyodide-lock.json)
for f in "${REQUIRED[@]}"; do
  [ -f "$CACHE/$f" ] || { echo "    missing in the Pyodide distribution: $f" >&2; exit 1; }
  cp "$CACHE/$f" "$OUT/pyodide/"
done
# The classic build, kept for browsers that will not take a module at all.
# Its absence is not fatal.
[ -f "$CACHE/pyodide.js" ] && cp "$CACHE/pyodide.js" "$OUT/pyodide/"

# Rename the .mjs files to .js and rewrite the one reference between them.
# Plenty of web servers do not know the .mjs extension and send it as
# application/octet-stream, which browsers refuse to load as a module - the page
# then dies halfway with a "failed to fetch dynamically imported module". The
# content is identical either way, and .js is understood everywhere.
echo "==> Renaming .mjs to .js (servers that do not know the extension)"
mv "$OUT/pyodide/pyodide.asm.mjs" "$OUT/pyodide/pyodide.asm.js"
mv "$OUT/pyodide/pyodide.mjs" "$OUT/pyodide/pyodide.module.js"
for f in "$OUT/pyodide/pyodide.module.js" "$OUT/pyodide/pyodide.js" \
         "$OUT/pyodide/pyodide.asm.js"; do
  [ -f "$f" ] && sed -i 's/pyodide\.asm\.mjs/pyodide.asm.js/g' "$f"
done

echo "==> Copying wheels"
for name in "${WHEELS[@]}"; do
  found=$(find "$CACHE" -maxdepth 1 -iname "${name}-*.whl" | head -1)
  if [ -n "$found" ]; then cp "$found" "$OUT/pyodide/"
  else echo "    missing: $name" >&2; fi
done

echo "==> Packing the analysis"
rm -f build/app.zip
# Everything the readers, the analysis and the template need at runtime.
zip -qr build/app.zip loop_cr_review.py _version.py lcr templates locale \
    -x '*__pycache__*' -x '*.po'
(cd poc/browser-pyodide && zip -q ../../build/app.zip browser_entry.py)
cp build/app.zip "$OUT/app.zip"
cp poc/browser-pyodide/index.html "$OUT/index.html"

# Browsers refuse to load WebAssembly from a file:// path, so the folder has to
# be served - which is not obvious to someone who just unpacked a ZIP.
cat > "$OUT/README.txt" <<'TXT'
Loop-CR-Review - browser build
==============================

Everything runs in the browser tab: the export is not uploaded, and once the
page has loaded, nothing goes over the network.

Browsers will not load WebAssembly from a file:// path, so this folder has to be
served over HTTP. Two ways:

  Locally, for a quick look
    cd into this folder and run
        python3 -m http.server 8000
    then open  http://localhost:8000/

  On your own web server
    copy this folder into the document root and open it in a browser.
    Nothing is executed on the server - it only hands out the files.

No medical device, no dosing advice. Material for the conversation with the
diabetes team.
TXT

echo "==> Packaging"
rm -f dist/loop-cr-review-browser-poc.zip
(cd dist && zip -qr loop-cr-review-browser-poc.zip browser-pyodide)

echo "==> Verifying"
for f in index.html app.zip pyodide/pyodide.module.js pyodide/pyodide.asm.js \
         pyodide/pyodide.asm.wasm pyodide/python_stdlib.zip pyodide/pyodide-lock.json; do
  [ -s "$OUT/$f" ] || { echo "    missing or empty: $f" >&2; exit 1; }
done
for name in numpy matplotlib jinja2; do
  ls "$OUT"/pyodide/${name}-*.whl >/dev/null 2>&1 \
    || { echo "    no wheel for $name" >&2; exit 1; }
done
echo "    all required files present"

echo "==> Done"
du -sh "$OUT" dist/loop-cr-review-browser-poc.zip | sed 's/^/    /'
echo "    serve the folder over HTTP - see $OUT/README.txt"
