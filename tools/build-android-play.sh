#!/usr/bin/env bash
# Build the Google Play Android App Bundle (same bake as the sideload APK).
#
# Usage:  ./tools/build-android-play.sh
# Keystore password: android/release.env (gitignored) or a prompt.
#
# Needs JDK 17, Android SDK (ANDROID_HOME or ANDROID_SDK_ROOT), and the
# release keystore (same as ./tools/build-android-apk.sh).
#
# Writes:  dist/loop-cr-review-play.aab
#
# Upload that file in Play Console → the existing app
# de.peisenh.loopcrreview → internal / closed testing. Play wants AAB,
# not the sideload APK. versionName comes from git describe; versionCode
# from android/app/build.gradle.kts (override with PLAY_VERSION_CODE).
set -euo pipefail

cd "$(dirname "$0")/.."
APP="android"
OUT="dist/loop-cr-review-play.aab"

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
ABI="${ANDROID_ABI:-arm64-v8a,x86_64}"

cp -f _version.py build-version.bak 2>/dev/null || true
echo "VERSION = \"$VERSION\"" > _version.py
restore_version() {
  if [ -f build-version.bak ]; then mv -f build-version.bak _version.py
  else git checkout -- _version.py 2>/dev/null || true; fi
}
trap restore_version EXIT INT TERM

echo "==> SDK $SDK"
echo "==> version $VERSION  abi $ABI  (Play AAB)"
# Password from CI env, android/release.env, or a silent prompt — not argv.
# shellcheck source=android-keystore-env.sh
source "$(dirname "$0")/android-keystore-env.sh"

GRADLE_PROPS=(-PappVersion="$VERSION" -Pabi="$ABI")
if [ -n "${PLAY_VERSION_CODE:-}" ]; then
  GRADLE_PROPS+=(-PversionCode="$PLAY_VERSION_CODE")
  echo "==> versionCode override $PLAY_VERSION_CODE"
fi

echo "==> bundling signed release AAB"
echo "==> keystore $ANDROID_KEYSTORE  alias $ANDROID_KEY_ALIAS"

"$APP/gradlew" -p "$APP" --no-daemon \
  bundleRelease \
  "${GRADLE_PROPS[@]}"

AAB="$APP/app/build/outputs/bundle/release/app-release.aab"
[ -f "$AAB" ] || {
  echo "Gradle finished but $AAB is missing." >&2
  exit 1
}
cp -f "$AAB" "$OUT"
echo "==> $OUT  ($(wc -c < "$OUT") bytes)"
echo "==> Play Console → de.peisenh.loopcrreview → Closed testing → upload this AAB"
