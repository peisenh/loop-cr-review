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

Works on **4 KB and 16 KB** page-size devices. The APK ships numpy **2.3.2**
from [Chaquopy pypi-upstream](https://chaquo.com/pypi-upstream/numpy/) plus a
matplotlib wheel committed in [`app/wheels/`](app/wheels/) (ELF `PT_LOAD`
align `0x4000`). Play upload is no longer blocked by native-lib alignment;
listing on Play is a separate decision.

Notices for bundled third-party code: [`app/wheels/NOTICE.md`](app/wheels/NOTICE.md).
Background: [docs/android-poc.md](../docs/android-poc.md).

## Build

Needs JDK 17 and an Android SDK (`ANDROID_HOME` or `ANDROID_SDK_ROOT`).
From the **repository root**:

```bash
./tools/build-android-apk.sh
# → dist/loop-cr-review-android.apk
```

That is the same command GitHub Actions runs on a `v*` tag. The workflow also
builds the Play bundle and, when `PLAY_SERVICE_ACCOUNT_JSON` is configured,
uploads it to the **internal** track as a draft — no review, nobody outside the
internal tester list, and the closed test stays where it is. Without the secret
the step is skipped and the tag still produces its artifacts.

Setting that up: create a service account in Google Cloud, invite it in the Play
Console under Users and permissions with "Manage testing track releases", and put
its JSON key in the repository secret. The link takes a while to become
effective, so the first attempt often fails on permissions with nothing actually
misconfigured.

**arm64-v8a only.** numpy and matplotlib have to be 16 KB aligned to load on
current devices, and that alignment turns out to be a toolchain default for arm64
and nothing else — no combination of linker flags produced an aligned x86_64
wheel, which `poc/android-x86_64-16k/` records. Shipping an x86_64 slice that
cannot load its own libraries would be worse than shipping none. The emulator
runs arm64 translated; `-Pabi=` still overrides the default for anyone who wants
to try. The committed matplotlib wheel is arm64-only, and numpy is downloaded
during the build (not in git).

Rebuild matplotlib (rare):

```bash
./tools/build-matplotlib-android-wheel.sh
# replaces android/app/wheels/matplotlib-*.whl — commit that file
```

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
