# The Android matplotlib wheel

**Retired.** The charts are drawn as SVG now (`lcr/svg.py`), so the app has no
matplotlib and this wheel is not built or shipped any more. The script is kept
here because it worked, it took a while to get right, and nothing about the
problem it solved has gone away for anyone else facing it.

## What the problem was

Chaquopy's public index carries matplotlib built against numpy 1.x. numpy 1.x
bundles OpenBLAS, whose `libgfortran` is 4 KB aligned, and a device with 16 KB
memory pages refuses to map it — the app fails to start, naming the library and
nothing else.

numpy **2.3.2** from <https://chaquo.com/pypi-upstream/> is 16 KB aligned for
arm64 and solves that. But then matplotlib has to be built against numpy 2: a
module compiled against one major version does not load with the other.

There was no such wheel. So it was built here.

## What the script does

`build-matplotlib-android-wheel.sh` cross-compiles matplotlib for
`android_24_arm64_v8a` with cibuildwheel, against a pinned numpy, using the
Android toolchain that cibuildwheel downloads rather than the one in
`ANDROID_HOME` — a distinction that cost an afternoon, because a check on the
NDK version in `$ANDROID_HOME` proves nothing about what actually compiles.

The result was committed to `android/app/wheels/` and installed via
`--find-links`, since it exists on no index.

## What it cost

- One 10 MB binary in git, replaced on every matplotlib or numpy bump.
- A version coupling: change numpy, rebuild matplotlib, or the app stops
  starting.
- arm64 only. The same build for x86_64 never produced a 16 KB aligned wheel;
  three approaches failed and are recorded in
  [`../android-x86_64-16k/`](../android-x86_64-16k/). The APK ships arm64 alone
  because of it.

## Why it is retired rather than fixed

None of the above is matplotlib's fault, and none of it would have been solved
by trying harder. The report asks for bands, lines, a few labels and a pair of
axes; drawing those as SVG needs about 250 lines and no compiler. What that
change involved is in [`../svg-charts/`](../svg-charts/).

With matplotlib gone, numpy is the only compiled dependency left — and the point
of removing it too is that nothing in the app would be compiled at all.

## Licence

matplotlib is distributed under the Matplotlib / PSF-based licence,
[`LICENSE-matplotlib`](LICENSE-matplotlib). Copyright remains with the
Matplotlib Development Team. The script here is part of this project and
AGPL-3.0-or-later like the rest of it.
