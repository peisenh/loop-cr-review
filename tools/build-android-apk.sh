#!/usr/bin/env bash
# Build the sideload Android APK locally (same flags as the release workflow).
#
# Usage:  ./tools/build-android-apk.sh
# Keystore password: android/release.env (gitignored) or a prompt.
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
  echo "  sdkmanager \"platforms;android-36\" \"build-tools;36.0.0\" \"platform-tools\"" >&2
  exit 1
}

mkdir -p "$APP" dist
printf 'sdk.dir=%s\n' "$SDK" > "$APP/local.properties"

VERSION="$(git describe --tags --always --dirty 2>/dev/null || echo poc)"
# Both ABIs by default. x86_64 is only useful for the emulator, but it lets
# that run natively, and Play splits a bundle so no device downloads both.
ABI="${ANDROID_ABI:-arm64-v8a,x86_64}"

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
# Password from CI env, android/release.env, or a silent prompt — not argv.
# shellcheck source=android-keystore-env.sh
source "$(dirname "$0")/android-keystore-env.sh"

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

# The wheels are checked one by one when they are built, but only the finished
# package shows what a device actually loads — Chaquopy's own libraries and the
# Python runtime come in here too. zipalign -P 16 checks that every library sits
# on a 16 KB boundary inside the archive; a device with 16 KB pages refuses to
# map one that does not, naming the library and nothing else.
# Newest build-tools, sorted by version rather than by name: 9.0.0 sorts after
# 36.0.0 alphabetically.
ZIPALIGN="$(ls -1d "$SDK"/build-tools/*/ 2>/dev/null | sort -V | tail -1)zipalign"
[ -x "$ZIPALIGN" ] || ZIPALIGN=""
if [ -z "$ZIPALIGN" ]; then
  echo "==> no zipalign in $SDK/build-tools — skipping the alignment check" >&2
else
  echo "==> checking 16 KB alignment"
  if ! "$ZIPALIGN" -c -P 16 4 "$OUT"; then
    echo "The APK has libraries that are not 16 KB aligned. They will not load on" >&2
    echo "a device with 16 KB pages. Nothing here is compiled any more, so this" >&2
    echo "would mean something in the Chaquopy runtime itself." >&2
    exit 1
  fi
  echo "    all libraries 16 KB aligned"
fi
