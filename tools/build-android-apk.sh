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
APP="poc/android-chaquopy"
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

echo "==> SDK $SDK"
echo "==> version $VERSION  abi $ABI"
echo "==> assembling debug APK (sideload, 4 KB page-size wheels)"

"$APP/gradlew" -p "$APP" --no-daemon \
  assembleDebug \
  -PappVersion="$VERSION" \
  -Pabi="$ABI"

APK="$APP/app/build/outputs/apk/debug/app-debug.apk"
[ -f "$APK" ] || {
  echo "Gradle finished but $APK is missing." >&2
  exit 1
}
cp -f "$APK" "$OUT"
echo "==> $OUT  ($(wc -c < "$OUT") bytes)"
