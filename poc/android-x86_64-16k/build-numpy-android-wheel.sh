#!/usr/bin/env bash
# Rebuild an Android numpy wheel (16 KB ELF align) into android/app/wheels/.
#
# Experiment. Does not change Gradle, fetch-android-wheels.sh or the
# matplotlib pin. Run this when you want a numpy you built yourself
# instead of the pypi-upstream 2.3.2-1 wheel (whose x86_64 OpenBLAS is
# still 4 KB-aligned).
#
# Needs: Linux or macOS, Python 3.13, ANDROID_HOME, NDK r28+, network.
# First run clones numpy and takes a long time.
#
# Usage (repo root):
#   ./tools/build-numpy-android-wheel.sh
#   ANDROID_ABI=x86_64 ./tools/build-numpy-android-wheel.sh
#   NUMPY_REF=v2.3.2 ./tools/build-numpy-android-wheel.sh
#   NUMPY_NOBLAS=1 ./tools/build-numpy-android-wheel.sh   # no OpenBLAS
#
# NOBLAS is the right choice for this project rather than a fallback: the
# analysis has no dot, matmul or linalg anywhere — only element-wise work,
# medians and percentiles, none of which go through BLAS. chaquopy-openblas is
# also not installable from the upstream index.
#
# Writes: android/app/wheels/numpy-*-cp313-cp313-android_24_<abi>.whl
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

# libc++_shared.so is bundled from the NDK, not built here, and only became
# 16 KB aligned in r28. An older NDK produces a wheel that passes every step and
# is then refused by the linker on the device.
NDK_MIN=28
NDK_BEST=""
for d in "$SDK"/ndk/*/; do
  [ -f "$d/source.properties" ] || continue
  rev=$(sed -n 's/^Pkg.Revision *= *\([0-9]*\).*/\1/p' "$d/source.properties")
  [ -n "$rev" ] || continue
  if [ -z "$NDK_BEST" ] || [ "$rev" -gt "$NDK_BEST" ]; then
    NDK_BEST="$rev"; NDK_DIR="$d"
  fi
done
if [ -z "$NDK_BEST" ]; then
  echo "No NDK under $SDK/ndk. Install r$NDK_MIN or newer via the SDK Manager." >&2
  exit 1
fi
if [ "$NDK_BEST" -lt "$NDK_MIN" ]; then
  # A warning, not a refusal: cibuildwheel brings its own Android toolchain with
  # the Python distribution it downloads, so this NDK may not be the one that
  # ends up compiling anything. The alignment check at the end is what actually
  # decides, and it looks at the wheel rather than at the toolchain.
  echo "warning: newest NDK here is r$NDK_BEST; r$NDK_MIN+ aligns libc++_shared" >&2
  echo "         to 16 KB. Whether it matters depends on which toolchain" >&2
  echo "         cibuildwheel uses — the check at the end will tell." >&2
fi
export ANDROID_NDK_ROOT="${ANDROID_NDK_ROOT:-${NDK_DIR%/}}"
echo "==> NDK r$NDK_BEST at $ANDROID_NDK_ROOT"

# 2.5.2 is current on PyPI; it has no [tool.cibuildwheel.android] yet.
# Overrides below are taken from numpy main (PR #30412).
NUMPY_REF="${NUMPY_REF:-v2.5.2}"
ABI="${ANDROID_ABI:-arm64-v8a}"
case "$ABI" in
  arm64-v8a) CIBW_ONLY="cp313-android_arm64_v8a" ;;
  x86_64)    CIBW_ONLY="cp313-android_x86_64" ;;
  *)
    echo "ANDROID_ABI must be arm64-v8a or x86_64 (got $ABI)." >&2
    exit 1
    ;;
esac

WORKDIR="${NPY_WHEEL_WORKDIR:-$PWD/.numpy-android-build}"
WHEELHOUSE="$PWD/android/app/wheels"
VENV="$WORKDIR/venv"
INDEX="${PIP_EXTRA_INDEX_URL:-https://chaquo.com/pypi-upstream/}"
OPENBLAS_PIN="${CHAQUOPY_OPENBLAS:-0.3.33}"
mkdir -p "$WORKDIR" "$WHEELHOUSE"

echo "==> SDK $ANDROID_HOME"
echo "==> numpy $NUMPY_REF  $CIBW_ONLY  noblas=${NUMPY_NOBLAS:-0}"

if [ ! -x "$VENV/bin/python" ]; then
  echo "==> creating $VENV"
  "$PY_SYS" -m venv "$VENV"
fi
PY="$VENV/bin/python"

"$PY" -m pip install -U pip cibuildwheel

if [ ! -d "$WORKDIR/numpy/.git" ]; then
  git clone --filter=blob:none https://github.com/numpy/numpy.git "$WORKDIR/numpy"
fi
git -C "$WORKDIR/numpy" fetch --tags --depth 1 origin "$NUMPY_REF"
git -C "$WORKDIR/numpy" checkout --detach FETCH_HEAD
git -C "$WORKDIR/numpy" submodule update --init --depth 1
echo "==> at $(git -C "$WORKDIR/numpy" rev-parse --short HEAD)"

# Releases up to 2.3.x list cibuildwheel enable groups that current cibuildwheel
# no longer knows:
#   error: Unknown enable group: cpython-freethreading
# Only names it still accepts are kept. Nothing here builds free-threaded or
# PyPy wheels anyway — the build is selected with --only below.
"$PY" - <<'PY' "$WORKDIR/numpy/pyproject.toml"
import re, sys
from pathlib import Path

KNOWN = {"cpython-prerelease", "graalpy", "pypy", "pypy-eol",
         "pyodide-eol", "pyodide-prerelease"}
path = Path(sys.argv[1])
text = path.read_text()
match = re.search(r'^enable\s*=\s*\[([^\]]*)\]', text, re.M)
if not match:
    print("==> no cibuildwheel enable list to clean")
else:
    names = re.findall(r'"([^"]+)"', match.group(1))
    keep = [n for n in names if n in KNOWN]
    dropped = [n for n in names if n not in KNOWN]
    if not dropped:
        print("==> cibuildwheel enable list already understood")
    else:
        line = "enable = [" + ", ".join(f'"{n}"' for n in keep) + "]"
        path.write_text(text[:match.start()] + line + text[match.end():])
        print(f"==> dropped unknown enable groups: {', '.join(dropped)}")
PY

# numpy/_core/meson.build detects the `long double` representation by
# *running* a probe binary. Under cibuildwheel+meson-python the synthesized
# Android cross file sets needs_exe_wrapper=true, so meson refuses:
#   meson.build:507: ERROR: Can not run test applications in this cross environment.
# The probe is skipped when the external property is already set. numpy main
# hardcodes this per-platform; releases up to v2.5.2 do not, so supply it.
# Android: `long double` is IEEE binary128 on every 64-bit ABI, including
# x86_64 (clang's Android target overrides the SysV x87 80-bit format).
#   https://developer.android.com/ndk/guides/abis
CROSS="$WORKDIR/android-${ABI}.meson.cross"
cat > "$CROSS" <<'CROSSEOF'
[properties]
longdouble_format = 'IEEE_QUAD_LE'
CROSSEOF
echo "==> extra cross file $CROSS"
sed 's/^/    /' "$CROSS"
# 16 KB alignment is a linker default for arm64 only — the one ABI where Android
# devices use 16 KB pages. x86_64, which is what the emulator runs, has to be
# told. Not through LDFLAGS (meson ignores the host's when cross compiling) and
# not through a cross file either: meson-python appends its own cross file after
# ours, and the later one wins. A -D option beats both.
ALIGN_ARGS="setup-args=-Dc_link_args=-Wl,-z,max-page-size=16384"
ALIGN_ARGS="$ALIGN_ARGS setup-args=-Dcpp_link_args=-Wl,-z,max-page-size=16384"
EXTRA_SETUP_ARGS="setup-args=--cross-file=$CROSS $ALIGN_ARGS"


# 2.5.2 has no android cibuildwheel table. Inject the bits numpy main uses.
# NDK r28+ defaults to 16 KB max-page-size; keep the flag explicit anyway.
export ANDROID_API_LEVEL="${ANDROID_API_LEVEL:-24}"
export CIBW_TEST_SKIP='*'
export CIBW_BUILD_VERBOSITY="${CIBW_BUILD_VERBOSITY:-1}"
# The flag has to reach the link step, and it has to come last: the toolchain
# supplies its own -z max-page-size, and with that option the last one on the
# command line wins. So this appends to what cibuildwheel already puts in
# LDFLAGS rather than replacing it — $LDFLAGS is expanded in the build
# environment, not in this shell. The -D options above cover meson; this covers
# anything that goes through LDFLAGS instead.
# Single quotes on purpose: $LDFLAGS must survive this shell untouched and be
# expanded by cibuildwheel in the build environment. Double quotes made bash
# resolve it here, where it is unset — and with set -u that ends the run.
ANDROID_ENV='LDFLAGS="$LDFLAGS -Wl,-z,max-page-size=16384"'
# numpy's pyproject before-build installs scipy-openblas32 from PyPI and
# deletes .openblas. That package is not on the Android build. Replace it.
export CIBW_BEFORE_BUILD="true"
export CIBW_BEFORE_BUILD_ANDROID="true"

if [ "${NUMPY_NOBLAS:-0}" = 1 ]; then
  export CIBW_CONFIG_SETTINGS_ANDROID="$EXTRA_SETUP_ARGS setup-args=-Duse-ilp64=false setup-args=-Dallow-noblas=true setup-args=-Dblas=none setup-args=-Dlapack=none"
  echo "==> BLAS off (NUMPY_NOBLAS=1)"
else
  # {project} is not expanded in CIBW_ENVIRONMENT_ANDROID. Install on the
  # host into the numpy tree (visible to the Android build) and pass an
  # absolute PKG_CONFIG_PATH.
  OB_ROOT="$WORKDIR/numpy/.openblas"
  echo "==> pip install chaquopy-openblas==${OPENBLAS_PIN} → $OB_ROOT"
  "$PY" -m pip install --upgrade --target "$OB_ROOT" \
    --index-url "$INDEX" "chaquopy-openblas==${OPENBLAS_PIN}"
  mapfile -t PCS < <(find "$OB_ROOT" -name '*.pc' -print 2>/dev/null || true)
  if [ ${#PCS[@]} -eq 0 ]; then
    echo "no .pc after chaquopy-openblas install. layout:" >&2
    find "$OB_ROOT" -maxdepth 4 \( -name '*.so' -o -name '*.pc' -o -type d \) | head -40 >&2
    echo "retry with NUMPY_NOBLAS=1 to get a wheel without BLAS." >&2
    exit 1
  fi
  PC_DIR="$(dirname "${PCS[0]}")"
  echo "==> pkg-config dir $PC_DIR"
  for pc in "${PCS[@]}"; do echo "    $(basename "$pc")"; done
  export PKG_CONFIG_PATH="$PC_DIR${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
  ANDROID_ENV="$ANDROID_ENV PKG_CONFIG_PATH=${PC_DIR}"
  export CIBW_CONFIG_SETTINGS_ANDROID="$EXTRA_SETUP_ARGS setup-args=-Duse-ilp64=false setup-args=-Dallow-noblas=false"
  echo "==> OpenBLAS chaquopy-openblas==${OPENBLAS_PIN}"
fi

export CIBW_ENVIRONMENT_ANDROID="$ANDROID_ENV"
echo "==> build env: $CIBW_ENVIRONMENT_ANDROID"

(
  cd "$WORKDIR/numpy"
  "$PY" -m cibuildwheel --only "$CIBW_ONLY"
)

shopt -s nullglob
built=("$WORKDIR/numpy/wheelhouse"/numpy-*-android_24_*.whl)
[ ${#built[@]} -gt 0 ] || {
  echo "cibuildwheel finished but no android_24 wheel in wheelhouse/." >&2
  exit 1
}
cp -f "${built[@]}" "$WHEELHOUSE/"
echo "==> copied to $WHEELHOUSE"
ls -l "$WHEELHOUSE"/numpy-*.whl

echo
echo "==> checking ELF alignment"
python3 tools/check-wheel-alignment.py "${built[@]}"
