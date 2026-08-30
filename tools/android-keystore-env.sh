#!/usr/bin/env bash
# Load the Android release keystore password without putting it on the
# command line (shell history, ps). Sourced from the APK/AAB scripts.
#
# First match wins:
#   1. ANDROID_KEYSTORE_PASSWORD already in the environment (CI)
#   2. android/release.env  (gitignored; see release.env.example)
#   3. silent prompt
#
# Expects to run after: cd "$(dirname "$0")/.." and APP=android
if [ -z "${ANDROID_KEYSTORE_PASSWORD:-}" ]; then
  ENV_FILE="${ANDROID_KEYSTORE_ENV:-$PWD/$APP/release.env}"
  if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
fi
KS="${ANDROID_KEYSTORE:-$PWD/$APP/release.jks}"
if [ ! -f "$KS" ]; then
  echo "No release keystore at $KS" >&2
  echo "Create once: ./tools/make-android-keystore.sh" >&2
  echo "GitHub Actions needs secrets ANDROID_KEYSTORE_BASE64 and ANDROID_KEYSTORE_PASSWORD." >&2
  exit 1
fi
export ANDROID_KEYSTORE="$KS"
if [ -z "${ANDROID_KEYSTORE_PASSWORD:-}" ]; then
  printf "Keystore password: " >&2
  read -r -s ANDROID_KEYSTORE_PASSWORD
  echo >&2
fi
if [ -z "${ANDROID_KEYSTORE_PASSWORD:-}" ]; then
  echo "set ANDROID_KEYSTORE_PASSWORD or put it in android/release.env" >&2
  exit 1
fi
if [ -z "${ANDROID_KEY_ALIAS:-}" ]; then ANDROID_KEY_ALIAS=loopcr; fi
export ANDROID_KEY_ALIAS ANDROID_KEYSTORE_PASSWORD
export ANDROID_KEY_PASSWORD="${ANDROID_KEY_PASSWORD:-$ANDROID_KEYSTORE_PASSWORD}"
