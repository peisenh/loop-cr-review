# Android app — how it got here

The Gradle project now lives in `android/`. Until that move it was
`poc/android-chaquopy/` (git history still uses that path in older commits).

This page is only the trail. Build and device notes: [`android/README.md`](../android/README.md).

## Why an app

The goal was the same analysis **on the device**, with no server. A browser
build (Pyodide, `poc/browser-pyodide/`) cannot load WebAssembly from `file://`,
so “download it and it runs” does not work there. Termux could not satisfy the
scientific stack. Chaquopy embeds CPython in an APK; Flask serves the existing
UI on loopback; a WebView displays it.

## What was proven

- Full chain on a **4 KB** page-size device: Chaquopy, Python 3.13, numpy,
  matplotlib, Flask, WebView, report from a real export.
- Speed comparable to a modest desktop. Computation is not the blocker.
- `syncAnalysis` copies `loop_cr_review.py` and friends from the repo at
  build time. An early snapshot inside the app went stale immediately.

## 16 KB pages

Android 15+ can use 16 KB pages. Chaquopy 17 itself is fine; the **wheels**
are not, in combination:

| | numpy 1.26 (Chaquopy index) | numpy 2.3.2 (pypi-upstream) |
|--|--|--|
| 4 KB device | yes | yes |
| 16 KB device | no (`libgfortran` alignment) | yes |
| matplotlib that matches | yes | no |

Until there is a matplotlib Android wheel built against numpy 2, the APK is
sideload-only on 4 KB devices and cannot go to Play (16 KB requirement for
new apps targeting API 35).

`app/build.gradle.kts` stays on the pair that runs. The extra-index pin is
left as a comment.

## Fixed while bringing it up

- `Activity` instead of `AppCompatActivity` (plain platform theme).
- Cleartext allowed for `localhost`, `127.0.0.1` and `[::1]` — Android treats
  the names as different hosts.
- Pixel 8 file pick: copy `content://` into app cache before Flask sees it.
- Viewer chrome: system-bar insets on a wrapper, not on the WebView.
- Save: WebView has no download of its own; the first attachment response is
  intercepted and a system “save as” dialog is used.

## Still open

- Foreground service during a long analysis.
- Activity Result API instead of `startActivityForResult`.
- iOS is a separate toolchain (Chaquopy is Android-only).
