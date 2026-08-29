#!/usr/bin/env bash
# Download the Android numpy wheel into android/app/wheels/.
# matplotlib is committed there; do not overwrite it.
set -euo pipefail

cd "$(dirname "$0")/.."

DEST="android/app/wheels"
mkdir -p "$DEST"

ABI="${ANDROID_ABI:-arm64-v8a}"
ABI="${ABI%%,*}"
case "$ABI" in
  arm64-v8a) WHEEL_ARCH=arm64_v8a ;;
  x86_64)    WHEEL_ARCH=x86_64 ;;
  *)
    echo "ANDROID_ABI must be arm64-v8a or x86_64 (got $ABI)." >&2
    exit 1
    ;;
esac

shopt -s nullglob
mpl_existing=("$DEST"/matplotlib-*-android_24_${WHEEL_ARCH}.whl)
if [ ${#mpl_existing[@]} -ne 1 ]; then
  echo "Need exactly one matplotlib-*-android_24_${WHEEL_ARCH}.whl in $DEST." >&2
  echo "Build: ./tools/build-matplotlib-android-wheel.sh" >&2
  exit 1
fi
echo "==> matplotlib $(basename "${mpl_existing[0]}")"

NUMPY_VER="${NUMPY_ANDROID_VERSION:-2.3.2-1}"
NUMPY_URL="${NUMPY_WHEEL_URL:-https://chaquo.com/pypi-upstream/numpy/numpy-${NUMPY_VER}-cp313-cp313-android_24_${WHEEL_ARCH}.whl}"
numpy_wh="$DEST/$(basename "$NUMPY_URL")"

if [ "${FORCE_ANDROID_WHEELS:-}" = 1 ] || [ ! -f "$numpy_wh" ]; then
  echo "==> $(basename "$numpy_wh")"
  echo "    $NUMPY_URL"
  curl -fsSL --retry 3 -o "$numpy_wh.part" "$NUMPY_URL"
  mv -f "$numpy_wh.part" "$numpy_wh"
else
  echo "==> keep $(basename "$numpy_wh")"
fi

echo "==> $DEST"
ls -l "$DEST"/*.whl
