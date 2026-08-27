# Android app (Chaquopy) — proof of concept

**Status: open.** The approach holds. It has not been built or run on a device
from this repository — everything below about Gradle and Chaquopy comes from
reading the project, not from a build.

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

- Android Studio Hedgehog+ (or SDK 35 + JDK 17)
- Network on first Gradle sync (Chaquopy downloads Python + pip wheels)

## Build

1. Open **this directory** in Android Studio (not a parent folder).
2. Let Gradle sync; first Chaquopy/pip resolve can take several minutes.
3. Run on an **arm64** emulator or device (`arm64-v8a`). x86_64 emulators are also listed in `abiFilters`.
4. Debug variant: **Run → app**.

There is no Gradle Wrapper in this zip; Android Studio generates/uses its toolchain on import.

## What works in the prototype

- Local Flask UI (upload, options, report HTML)
- File picker for ZIP/CSV via WebChromeClient
- Stop server in `onDestroy`

## Known limits (before any production/store build)

- APK size will be large (numpy + matplotlib)
- Cold start: Python + Flask + first matplotlib font cache
- Long report generation with app backgrounded may be killed (no foreground service yet)
- Not a medical device; same disclaimer as the desktop tool

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

## Open before this could be more than a proof of concept

- **Build it.** Nothing here has been through Gradle.
- **APK size.** numpy and matplotlib through Chaquopy usually land at 60–100 MB
  per ABI; with two ABIs that wants measuring before anything is handed out.
- **Foreground service** during the report build, so Android does not kill a
  long analysis in the background.
- **Activity Result API** instead of the deprecated `startActivityForResult`.
- **iOS is a different road entirely.** Chaquopy is Android-only. Python 3.13
  supports iOS as a Tier 3 platform and BeeWare's Briefcase can build for it,
  but that is a second build chain, a developer account and App Store review —
  and without the store there is no way to hand the app out.

## Architecture

See [docs/architecture.md](docs/architecture.md).
