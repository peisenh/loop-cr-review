# Android app (Chaquopy) — proof of concept

**Status: it works on a 4 KB device.** Built, installed, and a report generated
on an API 34 emulator — roughly as fast as on a modest desktop machine, so the
computation is not the obstacle. On a device with a 16 KB memory page size numpy
cannot be loaded at all; see below. That is the one thing standing between this
and something usable.

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

1. Open **this directory** in Android Studio (not a parent folder).
2. Let Gradle sync; first Chaquopy/pip resolve can take several minutes.
3. Run on an **arm64** emulator or device (`arm64-v8a`). x86_64 emulators are also listed in `abiFilters`.
4. Debug variant: **Run → app**.

Open **this directory** in Android Studio — not a parent folder; the Gradle
project starts here. Studio provides its own Gradle and generates the wrapper on
import, which is why neither is checked in.

Run `./sync-analysis.sh` once before the first import: Gradle copies the analysis
before every *build*, but a project *sync* does not run that task, so the Python
folder would look empty until the first build.

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
  `onDestroy`.

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

numpy pulls in `libgfortran.so.3`, which Chaquopy ships built for 4 KB memory
pages. Android 15 and later can run with 16 KB pages, and recent emulator images
do so by default; the linker then refuses the library, numpy cannot be imported
and Flask never starts. Nothing in this project can fix that — it is Chaquopy's
prebuilt wheel (chaquo/chaquopy issue #1171, still open).

**Verified**: on an API 34 emulator (4 KB pages) the whole chain works — Python
starts, numpy and matplotlib import, Flask serves the form, and a report is
generated from an export at a speed comparable to a modest desktop. Use an API 34 image, a non-16 KB
API 35 image, or a phone on Android 14/15 without the 16 KB developer option.

**What it means beyond testing:** apps targeting API 35 and above have had to
support 16 KB pages to be published on Google Play since November 2025. As long
as Chaquopy's scientific wheels are 4 KB aligned, this app cannot go into the
Play Store at all. For a sideloaded APK on one's own phone it is only a matter
of which device.

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
