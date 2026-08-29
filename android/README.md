# Android app

Same analysis as the desktop tool, on the device. No server. Sideload only
(`loop-cr-review-android.apk` on the GitHub release).

Not a medical device — analysis only. No diagnosis, no treatment recommendation.

Application ID: `de.peisenh.loopcrreview`.

Flask runs on loopback inside the APK; a WebView shows that UI. Health data
never leaves the device (same ephemeral temp handling as the desktop web app).

```
Android app
  ├── Chaquopy Python runtime
  │     └── loop-cr-review + Flask → 127.0.0.1:<port>
  └── WebView → http://127.0.0.1:<port>/
```

## Devices

Works on **4 KB page-size** devices (Pixel 8 on Android 17 and Tab M11 were
used in testing). Does **not** run on 16 KB kernels: numpy and matplotlib
cannot be satisfied together on Chaquopy’s current wheels. Not for Play Store
until that exists. How that was found: [docs/android-poc.md](../docs/android-poc.md).

## Build

Needs JDK 17 and an Android SDK (`ANDROID_HOME` or `ANDROID_SDK_ROOT`).
From the **repository root**:

```bash
./tools/build-android-apk.sh
# → dist/loop-cr-review-android.apk
```

That is the same command GitHub Actions runs on a `v*` tag. Default ABI is
`arm64-v8a`. Both ABIs: `ANDROID_ABI=arm64-v8a,x86_64 ./tools/build-android-apk.sh`.

Or Android Studio: open **this directory** (`android/`), not the repo root.
Gradle copies the analysis before every *build* (`syncAnalysis`). A project
*sync* does not — run `./sync-analysis.sh` once before the first import.

```bash
./sync-analysis.sh            # copy the current analysis into the project
./sync-analysis.sh --check    # is the copy still current?
```

`app/src/main/python/` except `android_server.py` is generated and gitignored.


## Signing

Local builds and GitHub Releases use the **same** keystore so the Play
package registration (`de.peisenh.loopcrreview`) stays valid.

The keystore is **not** in git. Create it once on your machine:

```bash
ANDROID_KEYSTORE_PASSWORD='choose-a-password' ./tools/make-android-keystore.sh
# → android/release.jks
# prints ANDROID_KEYSTORE_BASE64 and a PEM for Play Console
```

Keep `android/release.jks` and the password offline (backup). Then in the
GitHub repo: Settings → Secrets and variables → Actions:

| Secret | Value |
|--------|--------|
| `ANDROID_KEYSTORE_BASE64` | the one-line base64 from the script |
| `ANDROID_KEYSTORE_PASSWORD` | same password |
| `ANDROID_KEY_ALIAS` | `loopcr` (optional; that is the default) |
| `ANDROID_KEY_PASSWORD` | only if the key password differs |

`./tools/build-android-apk.sh` signs `assembleRelease` with that file.
Without the keystore the script stops; a debug APK from Studio still works
but will not match the registered key.


## Limits

- Cold start loads Python, Flask and the first matplotlib font cache together.
- A long report with the app in the background may be killed (no foreground
  service).
- Save and “open in browser” are explicit; the raw export is deleted as soon
  as the report exists.
