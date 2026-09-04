#!/usr/bin/env bash
# Rebuild the Android matplotlib wheel against numpy 2.3.2 (16 KB ELF align).
#
# RETIRED: the charts are SVG now and the app ships no matplotlib. Kept
# because it worked and the problem it solves still exists elsewhere. See
# README.md next to this file.
#
# Chaquopy's public index only has matplotlib built for numpy 1.x. numpy 2.3.2
# from https://chaquo.com/pypi-upstream/ loads on 16 KB page-size devices, but
# then needs a matching matplotlib. This script is that rebuild — run it rarely,
# when the pin below changes. CI must NOT run this on every APK build.
#
# Needs: Linux or macOS, Python 3.13, ANDROID_HOME, NDK r28+, network.
#
# Usage (repo root):
#   ./poc/matplotlib-android-wheel/build-matplotlib-android-wheel.sh
#   ANDROID_ABI=x86_64 ./poc/matplotlib-android-wheel/build-matplotlib-android-wheel.sh
#
# Writes: android/app/wheels/matplotlib-*-cp313-cp313-android_24_<abi>.whl
set -euo pipefail

cd "$(dirname "$0")/.."

PY_SYS="${PYTHON:-python3.13}"
command -v "$PY_SYS" >/dev/null || {
  echo "Python 3.13 is required ($PY_SYS not on PATH)." >&2
  exit 1
}

SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [ -z "$SDK" ]; then
  for candidate in \
      "$HOME/Android/Sdk" \
      "$HOME/Library/Android/sdk" \
      /usr/lib/android-sdk; do
    if [ -d "$candidate" ]; then SDK="$candidate"; break; fi
  done
fi
[ -n "${SDK:-}" ] && [ -d "$SDK" ] || {
  echo "Android SDK not found. Set ANDROID_HOME." >&2
  exit 1
}
export ANDROID_HOME="$SDK"

# Release tag (GitHub can fetch this). Short SHAs like 8fb842c78 are not
# remote refs — do not use them as MATPLOTLIB_REF.
MATPLOTLIB_REF="${MATPLOTLIB_REF:-v3.11.1}"
NUMPY_PIN="${NUMPY_PIN:-2.3.2}"
ABI="${ANDROID_ABI:-arm64-v8a}"
case "$ABI" in
  arm64-v8a) CIBW_ONLY="cp313-android_arm64_v8a" ;;
  x86_64)    CIBW_ONLY="cp313-android_x86_64" ;;
  *)
    echo "ANDROID_ABI must be arm64-v8a or x86_64 (got $ABI)." >&2
    exit 1
    ;;
esac

WORKDIR="${MPL_WHEEL_WORKDIR:-$PWD/.mpl-android-build}"
WHEELHOUSE="$PWD/android/app/wheels"
VENV="$WORKDIR/venv"
CONSTRAINT="$WORKDIR/constraints.txt"
INDEX="${PIP_EXTRA_INDEX_URL:-https://chaquo.com/pypi-upstream/}"
mkdir -p "$WORKDIR" "$WHEELHOUSE"

echo "==> SDK $ANDROID_HOME"
echo "==> matplotlib $MATPLOTLIB_REF  numpy $NUMPY_PIN  $CIBW_ONLY"

# Isolated venv — system pip is PEP-668-blocked on Debian/Ubuntu.
if [ ! -x "$VENV/bin/python" ]; then
  echo "==> creating $VENV"
  "$PY_SYS" -m venv "$VENV"
fi
PY="$VENV/bin/python"

# Host isolation and Android xbuild-files must see the same numpy version.
# pypi-upstream only has 2.3.2; without this pin, pip takes 2.3.5 from PyPI
# and then fails to find that version for android_24.
printf 'numpy==%s\n' "$NUMPY_PIN" > "$CONSTRAINT"
export PIP_CONSTRAINT="$CONSTRAINT"
export PIP_EXTRA_INDEX_URL="$INDEX"
export PIP_PREFER_BINARY=1

"$PY" -m pip install -U pip cibuildwheel
"$PY" -m pip install "numpy==$NUMPY_PIN"

if [ ! -d "$WORKDIR/matplotlib/.git" ]; then
  git clone --filter=blob:none https://github.com/matplotlib/matplotlib.git \
    "$WORKDIR/matplotlib"
fi

git -C "$WORKDIR/matplotlib" fetch --tags --depth 1 origin "$MATPLOTLIB_REF"
git -C "$WORKDIR/matplotlib" checkout --detach FETCH_HEAD
echo "==> at $(git -C "$WORKDIR/matplotlib" rev-parse --short HEAD)"

# pypi-upstream only ships numpy 2.3.2; several matplotlib branches cap at <2.3.
"$PY" - <<'PY' "$WORKDIR/matplotlib/pyproject.toml"
from pathlib import Path
import re, sys
p = Path(sys.argv[1])
text = p.read_text()
new = re.sub(r"(numpy[^\"']*)<2\.3", r"\1<2.4", text)
if new == text:
    print("==> no numpy<2.3 bound to loosen")
else:
    p.write_text(new)
    print("==> loosened numpy upper bound to <2.4")
PY

export ANDROID_API_LEVEL=24
export CIBW_TEST_SKIP='*'
export CIBW_ENVIRONMENT_ANDROID="PIP_CONSTRAINT=${CONSTRAINT} PIP_EXTRA_INDEX_URL=${INDEX} PIP_PREFER_BINARY=1 PIP_ONLY_BINARY=:all:"

(
  cd "$WORKDIR/matplotlib"
  "$PY" -m cibuildwheel --only "$CIBW_ONLY"
)

shopt -s nullglob
built=("$WORKDIR/matplotlib/wheelhouse"/matplotlib-*-android_24_*.whl)
[ ${#built[@]} -gt 0 ] || {
  echo "cibuildwheel finished but no android_24 wheel in wheelhouse/." >&2
  exit 1
}
cp -f "${built[@]}" "$WHEELHOUSE/"
echo "==> copied to $WHEELHOUSE"
ls -l "$WHEELHOUSE"/matplotlib-*.whl
