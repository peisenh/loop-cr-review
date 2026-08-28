#!/usr/bin/env bash
# Copy the current analysis from the repository into the Android project.
#
# Gradle does this automatically before every build; this script exists so the
# same thing can be done - and checked - without Android Studio. Use --check to
# find out whether the copy in the project still matches the repository.
#
# Usage:  ./sync-analysis.sh [--check]
set -euo pipefail

cd "$(dirname "$0")"
REPO="$(cd ../.. && pwd)"
DEST="app/src/main/python"

[ -f "$REPO/loop_cr_review.py" ] || {
  echo "repository not found at $REPO - this project expects to sit in poc/ inside it" >&2
  exit 1; }

# android_server.py belongs to the app and stays; everything else here is a copy.
copy_into() {   # copy_into <target-dir>
  local out="$1"
  mkdir -p "$out"
  cp "$REPO"/loop_cr_review.py "$REPO"/_version.py "$REPO"/webapp.py "$out/"
  for d in lcr templates; do
    rm -rf "${out:?}/$d"
    cp -r "$REPO/$d" "$out/$d"
  done
  rm -rf "${out:?}/static"
  mkdir -p "$out/static"
  cp "$REPO"/static/*.svg "$out/static/"
  # Only the compiled catalogues are read at runtime.
  rm -rf "${out:?}/locale"
  mkdir -p "$out/locale"
  (cd "$REPO/locale" && find . -name "*.mo") | while read -r mo; do
    mkdir -p "$out/locale/$(dirname "$mo")"
    cp "$REPO/locale/$mo" "$out/locale/$mo"
  done
  find "$out" -name "__pycache__" -type d -prune -exec rm -rf {} +
}

if [ "${1:-}" = "--check" ]; then
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  copy_into "$tmp/python"
  # android_server.py is not part of the comparison: it is the app's own code.
  if diff -r -x "android_server.py" -x "__pycache__" "$tmp/python" "$DEST" >/dev/null 2>&1; then
    echo "analysis in the project matches the repository"
  else
    echo "analysis in the project is out of date - run ./sync-analysis.sh" >&2
    diff -r -q -x "android_server.py" -x "__pycache__" "$tmp/python" "$DEST" 2>&1 | head -10 >&2
    exit 1
  fi
  exit 0
fi

copy_into "$DEST"
echo "copied the analysis from $REPO"
find "$DEST" -type f | wc -l | xargs echo "  files in $DEST:"
