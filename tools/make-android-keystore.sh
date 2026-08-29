#!/usr/bin/env bash
# Create the sideload release keystore once. Keep the file and the password
# off git. The same file is what GitHub Actions uses (secret, base64).
#
# Usage:
#   ANDROID_KEYSTORE_PASSWORD='…' ./tools/make-android-keystore.sh
# Writes: android/release.jks
# Prints: base64 line for GitHub secret ANDROID_KEYSTORE_BASE64
#         PEM for Play Console "add public key"
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="${ANDROID_KEYSTORE:-$PWD/android/release.jks}"
ALIAS="${ANDROID_KEY_ALIAS:-loopcr}"
: "${ANDROID_KEYSTORE_PASSWORD:?set ANDROID_KEYSTORE_PASSWORD}"
if [ -f "$OUT" ]; then
  echo "Refusing to overwrite $OUT" >&2
  exit 1
fi
keytool -genkeypair -v \
  -keystore "$OUT" \
  -alias "$ALIAS" \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -storepass "$ANDROID_KEYSTORE_PASSWORD" \
  -keypass "${ANDROID_KEY_PASSWORD:-$ANDROID_KEYSTORE_PASSWORD}" \
  -dname "${ANDROID_KEY_DNAME:-CN=loop-cr-review, OU=sideload, O=peisenh, L=., ST=., C=DE}"
echo
echo "==> $OUT"
echo "==> GitHub secret ANDROID_KEYSTORE_BASE64:"
base64 -w0 "$OUT" 2>/dev/null || base64 "$OUT"
echo
echo
echo "==> PEM for Play Console:"
keytool -exportcert -rfc \
  -keystore "$OUT" \
  -alias "$ALIAS" \
  -storepass "$ANDROID_KEYSTORE_PASSWORD"
