# Android app (Chaquopy) — proof of concept

**Status: it works on a 4 KB device.** Built, installed, and a report generated
on an API 34 emulator — roughly as fast as on a modest desktop machine, so the
computation is not the obstacle. On a device with a 16 KB memory page size numpy
cannot be loaded at all with the wheels from Chaquopy's own index. A newer numpy
from `pypi-upstream` settles that, but then there is no matching matplotlib to be
had anywhere. See below.

Built because the browser build could not meet the actual goal: browsers refuse
to load WebAssembly from a `file://` path, so "download it and it runs" does not
work there. An app brings its own runtime and needs no server at all.


Embeds the existing Python/Flask web app in an APK (Chaquopy) and shows it in a WebView on loopback only.

```
Android app
  ├── Chaquopy Python runtime
  │     └── loop-cr-review + Flask → 127.0.0.1:<port>
  └── WebView → http://127.0.0.1:<port>/
```

Application ID: `de.peisenh.loopcrreview`.

No remote backend. Health data stays on device (same ephemeral temp handling as the desktop web app).

## Requirements

- Android Studio (recent version); it brings its own JDK and Gradle
- SDK Platform 35 and Build-Tools 35, installed through the SDK Manager
- Network on the first Gradle sync — Chaquopy downloads Python and the pip wheels
- For a device over USB: `sudo apt install android-sdk-platform-tools-common`
  (udev rules), and add yourself to the `plugdev` group
- For the emulator: KVM (`qemu-kvm`, `libvirt-daemon-system`) and membership in
  the `kvm` group

## Build

From the **repository root** (JDK 17 + Android SDK, `ANDROID_HOME` set):

```bash
./tools/build-android-apk.sh
# → dist/loop-cr-review-android.apk
```

That is the same command GitHub Actions runs on a `v*` tag. Default ABI is
`arm64-v8a` (phones/tablets). Both ABIs: `ANDROID_ABI=arm64-v8a,x86_64 ./tools/build-android-apk.sh`.

Or Android Studio: open **this directory** (not a parent folder). Gradle
copies the analysis before every *build* (`syncAnalysis`); a project *sync*
does not, so run `./sync-analysis.sh` once before the first import.

The wrapper (`gradlew`) is in git so a machine without Studio can still build.

## What works — measured on an API 34 emulator

- The whole chain: Chaquopy, Python, numpy, matplotlib, Flask, WebView, and a
  report generated from a real export.
- **Speed**: about the pace of a modest desktop machine. Whatever stands in the
  way of this becoming useful, it is not the computation.
- **APK: 60 MB** — debug build, both ABIs, unoptimised. A single ABI should
  roughly halve that, and a release build with shrinking takes off a little more.
- **`syncAnalysis` runs as part of the build**, so the analysis inside the APK is
  the one from the repository. That was the point of the whole arrangement, and
  it is now demonstrated rather than assumed.
- File picker for ZIP/CSV through `WebChromeClient`; the server is stopped in
  `onDestroy`. On Pixel 8 / Android 17 the pick is copied into app cache first
  so Flask gets a real `.zip` / `.csv` rather than an unreadable `content://`
  URI.

## Known limits (before any production/store build)

- Cold start: Python, Flask and the first matplotlib font cache all at once.
- A long report with the app in the background may be killed — no foreground
  service yet.
- Not a medical device; same disclaimer as the desktop tool.

## The analysis is not copied

The first version of this proof of concept carried a snapshot of
`loop_cr_review.py`: 2243 lines, the state before the package split, several
releases behind — and nothing would ever have pulled it forward. Two truths, one
of them silently wrong.

It is taken from the repository at build time now:

```
./sync-analysis.sh            # copy the current analysis into the project
./sync-analysis.sh --check    # is the copy still current?
```

Gradle runs the same copy before every build (`syncAnalysis`, wired into
`preBuild`), so a build cannot pick up a stale snapshot. The copied paths under
`app/src/main/python/` are ignored by git; `android_server.py` is the app's own
code and is versioned here.

## Package versions are not the desktop ones

Chaquopy builds its own wheels for Android, and the scientific packages lag well
behind. Pinning the versions from `requirements.txt` stops the build outright:

    Could not find a version that satisfies the requirement numpy==2.3.5
    (from versions: 1.26.2)

So `numpy` and `matplotlib` are left unpinned here and pip takes what Chaquopy
has; only the pure-Python packages are pinned.

That is safe as far as it was checked: with **numpy 1.26.2 and matplotlib
3.8.4** the whole test suite passes and the generated report is *text-identical*
to the one built with numpy 2.x — only the chart rasterisation differs, as it
does between any two matplotlib builds. Worth re-checking whenever the analysis
starts using something newer.

## It does not run on a 16 KB page size device

Built, installed and started on an emulator — and then:

    E linker : ".../requirements/chaquopy/lib/libgfortran.so.3"
               program alignment (4096) cannot be smaller than system page size (16384)

Android 15 and later can run with 16 KB memory pages, and recent emulator images
do so by default. Native libraries built for 4 KB pages are refused by the linker.

**Chaquopy itself is not the problem.** Version 17.0.0 — the one this project
uses — supports 16 KB pages; issue #1171 is resolved on that side. Its changelog
adds the part that bites here:

> Devices with 16 KB pages are now supported by Chaquopy itself. However, many
> existing Android wheels will still fail to load on 16 KB devices. For best
> compatibility with these devices, use Python 3.13 or later.

This project already runs Python 3.13, so it is on the recommended setup, and the
build still resolved numpy to **1.26.2** ("from versions: 1.26.2"), whose bundled
`libgfortran.so.3` predates the October 2024 rebuilds.

**A newer numpy does exist.** `chaquo.com/pypi-upstream/numpy/` lists
`numpy-2.3.2-1-cp313-cp313-android_24_arm64_v8a.whl` and the matching
`android_24_x86_64.whl`, both dated December 2025 — so for both ABIs, and built
well after the October 2024 cut-off. A wheel of that age is very likely 16 KB
aligned.

The build did not use it. Chaquopy searches `pypi.org/simple` and its own
`pypi-13.1` index, where the newest numpy is 1.26.2; `pypi-upstream` is a
separate index and does not appear to be searched by default.

### Tried: numpy works, matplotlib has no matching build

Tried by adding the index and pinning the version:

```kotlin
options("--extra-index-url", "https://chaquo.com/pypi-upstream")
install("numpy==2.3.2")
```

**numpy 2.3.2 installs and loads.** The `libgfortran` failure is gone, so a
recent wheel really does settle the 16 KB question.

**matplotlib then no longer matches.** pip keeps taking it from Chaquopy's own
index, where it is compiled against numpy 1:

    ImportError: numpy.core.multiarray failed to import
      at matplotlib.transforms (transforms.py:49)

numpy 2 renamed that module to `numpy._core`, so an extension built against
numpy 1 cannot load it.

**And there is nowhere else to get one.** `pypi-upstream` carries
chaquopy-openblas, numpy, pandas, scikit-learn, scipy and xgboost — no
matplotlib. PyPI itself has no Android wheels for matplotlib at all (nor for
numpy), across every release. So the two cannot be satisfied together today:

| | numpy 1.26 (Chaquopy index) | numpy 2.3.2 (pypi-upstream) |
|---|---|---|
| loads on 4 KB device | yes | yes |
| loads on 16 KB device | **no** (`libgfortran`) | yes |
| matplotlib available | yes | **no** |

The condition to watch is a single one: **a matplotlib for Android built against
numpy 2.** Until that exists, this runs on 4 KB devices with numpy 1.26 and
nowhere else.

`app/build.gradle.kts` is therefore back on the combination that works — no
extra index, nothing pinned — with those two lines kept as a comment. Leaving
them active would have meant committing a proof of concept that does not run at
all.

**Verified**: on an API 34 emulator (4 KB pages) the whole chain works — Python
starts, numpy and matplotlib import, Flask serves the form, and a report is
generated from an export at a speed comparable to a modest desktop. Use an API 34
image, a non-16 KB API 35 image, or a phone on Android 14/15 without the 16 KB
developer option.

**What it means beyond testing:** Google Play has required apps targeting
Android 15+ to support 16 KB pages for new releases since November 2025, and for
updates from May 2026. Until the numpy wheel is rebuilt, this app could not go
there. For a sideloaded APK it is a question of which device — and that window
narrows with every new one.

## Fixed on the way to the first run

Two things the original proof of concept could not have worked with, both found
only by actually building it:

- **The activity used `AppCompatActivity` with a plain platform theme.** That
  throws "You need to use a Theme.AppCompat theme" the moment `setContentView`
  runs. The app is a WebView container and needs none of AppCompat, so it extends
  `Activity` now and the dependency is gone.
- **Cleartext was permitted for `localhost` only**, while the WebView is pointed
  at `http://127.0.0.1:<port>/`. Android treats the name and the numeric address
  as separate entries, so it failed with `ERR_CLEARTEXT_NOT_PERMITTED`. All three
  loopback spellings are listed now.

Startup errors used to go into a Toast, which truncates the message and is gone
in seconds — the traceback goes to the log and onto the screen instead.

## Open before this could be more than a proof of concept

- **Build it.** Nothing here has been through Gradle.
- **Foreground service** during the report build, so Android does not kill a
  long analysis in the background.
- **Activity Result API** instead of the deprecated `startActivityForResult`.
- **iOS is a different road entirely.** Chaquopy is Android-only. Python 3.13
  supports iOS as a Tier 3 platform and BeeWare's Briefcase can build for it,
  but that is a second build chain, a developer account and App Store review —
  and without the store there is no way to hand the app out.

## Architecture

See [docs/architecture.md](docs/architecture.md).
