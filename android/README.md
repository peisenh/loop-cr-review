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

Works on **4 KB and 16 KB** page-size devices, and the question no longer
really arises: the APK carries no compiled code of its own. The charts are SVG
and the arithmetic is plain Python, so numpy and the hand-built matplotlib wheel
that preceded it are both gone. What is left — Flask, Jinja2, waitress — is pure
Python, resolved by Chaquopy at build time.

Notices for bundled third-party code: [`NOTICE.md`](NOTICE.md).
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
uploads it to the **internal** track and publishes it there — no review, nobody
outside the internal tester list, and the closed test stays where it is. A draft
would have to be published by hand before it could be promoted to another track,
which is a step for no gain when the track reaches nobody else anyway. Without the secret
the step is skipped and the tag still produces its artifacts.

### The 16 KB check

`build-android-apk.sh` runs `zipalign -c -P 16` on the finished APK. The wheels
are checked one by one when they are built, but only the package shows what a
device actually loads: Chaquopy's own libraries and the Python runtime arrive
here too, and none of them pass through that earlier check.

The two checks look at different things and both matter. `zipalign` checks where
a library sits **inside the archive**; the wheel check reads the **ELF headers**
to see what alignment the library itself declares. A library can satisfy one and
fail the other.

It is skipped rather than failed when no build-tools are installed, so the build
still works on a machine that only has the SDK platform.

### Release notes for the store

`android/whatsnew/whatsnew-<locale>` — one file per store language, uploaded with
the bundle. Written by hand rather than generated from the changelog: that one is
for whoever reads the code, and a tester wants to know what changed for them, in
their language. They have to be committed before the tag, since the workflow
reads them out of it.

Play silently truncates at 500 characters and the cut lands mid-sentence, so the
workflow counts first and fails rather than publishing half a sentence. Umlauts
count as one each, as does the trailing newline.

Setting that up: create a service account in Google Cloud, invite it in the Play
Console under Users and permissions with "Manage testing track releases", and put
its JSON key in the repository secret. The link takes a while to become
effective, so the first attempt often fails on permissions with nothing actually
misconfigured.

**arm64-v8a by default**, but no longer of necessity. That restriction existed
because numpy had to be 16 KB aligned and only arm64 got that from the toolchain
— every attempt at an aligned x86_64 wheel failed, which
`poc/android-x86_64-16k/` records. With no native code of our own the constraint
is gone; the default is kept until a build for the other ABIs has actually been
tried, and `-Pabi=` overrides it.

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

- Cold start loads Python and Flask.
- A long report with the app in the background may be killed (no foreground
  service).
- Save and “open in browser” are explicit; the raw export is deleted as soon
  as the report exists.
