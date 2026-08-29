#!/usr/bin/env bash
# Build the sideload Android APK locally (same flags as the release workflow).
#
# Usage:  ./tools/build-android-apk.sh
#
# Needs JDK 17 and an Android SDK (ANDROID_HOME or ANDROID_SDK_ROOT).
# First run downloads Gradle, the SDK platforms if missing, and the
# Chaquopy Python/wheel set — several minutes, needs the network.
#
# Writes:  dist/loop-cr-review-android.apk
set -euo pipefail

cd "$(dirname "$0")/.."
APP="android"
OUT="dist/loop-cr-review-android.apk"

command -v java >/dev/null || {
  echo "JDK 17 is required (java not on PATH)." >&2
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
[ -n "$SDK" ] && [ -d "$SDK" ] || {
  echo "Android SDK not found. Set ANDROID_HOME to the SDK directory." >&2
  echo "  sdkmanager \"platforms;android-35\" \"build-tools;35.0.0\" \"platform-tools\"" >&2
  exit 1
}

mkdir -p "$APP" dist
printf 'sdk.dir=%s\n' "$SDK" > "$APP/local.properties"

VERSION="$(git describe --tags --always --dirty 2>/dev/null || echo poc)"
# Phones and tablets: one ABI. x86_64 is only useful for the emulator.
ABI="${ANDROID_ABI:-arm64-v8a}"

# Same bake as the desktop binaries: the APK has no git, so tool_version()
# only sees _version.py. Leave the placeholder and the report prints
# "Created with Loop-CR-Review" with nothing after it.
cp -f _version.py build-version.bak 2>/dev/null || true
echo "VERSION = \"$VERSION\"" > _version.py
restore_version() {
  if [ -f build-version.bak ]; then mv -f build-version.bak _version.py
  else git checkout -- _version.py 2>/dev/null || true; fi
}
trap restore_version EXIT INT TERM

echo "==> SDK $SDK"
echo "==> version $VERSION  abi $ABI"
KS="${ANDROID_KEYSTORE:-$PWD/$APP/release.jks}"
if [ ! -f "$KS" ]; then
  echo "No release keystore at $KS" >&2
  echo "Create once: ./tools/make-android-keystore.sh" >&2
  echo "GitHub Actions needs secrets ANDROID_KEYSTORE_BASE64 and ANDROID_KEYSTORE_PASSWORD." >&2
  exit 1
fi
export ANDROID_KEYSTORE="$KS"
: "${ANDROID_KEYSTORE_PASSWORD:?set ANDROID_KEYSTORE_PASSWORD}"
if [ -z "${ANDROID_KEY_ALIAS:-}" ]; then ANDROID_KEY_ALIAS=loopcr; fi
export ANDROID_KEY_ALIAS ANDROID_KEYSTORE_PASSWORD
export ANDROID_KEY_PASSWORD="${ANDROID_KEY_PASSWORD:-$ANDROID_KEYSTORE_PASSWORD}"

echo "==> fetching numpy Android wheel"
./tools/fetch-android-wheels.sh

echo "==> assembling signed release APK (16 KB-aligned wheels)"
echo "==> keystore $ANDROID_KEYSTORE  alias $ANDROID_KEY_ALIAS"

"$APP/gradlew" -p "$APP" --no-daemon \
  assembleRelease \
  -PappVersion="$VERSION" \
  -Pabi="$ABI"

APK="$APP/app/build/outputs/apk/release/app-release.apk"
[ -f "$APK" ] || {
  echo "Gradle finished but $APK is missing." >&2
  exit 1
}
cp -f "$APK" "$OUT"
echo "==> $OUT  ($(wc -c < "$OUT") bytes)"
