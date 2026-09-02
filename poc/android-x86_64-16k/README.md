# numpy for Android x86_64 with 16 KB alignment — proof of concept

**Status: not pursued.** The wheel builds, and it is still 4 KB aligned.

## What was asked

The emulator runs x86_64. To test the app there against a 16 KB page size image,
numpy and matplotlib need to be built for that ABI with their libraries aligned
to 16 KB — `chaquo.com/pypi-upstream` has numpy 2.3.2 for x86_64, but its
OpenBLAS is 4 KB aligned and the linker refuses it on such a device.

## What was built

`build-numpy-android-wheel.sh` builds numpy from source with cibuildwheel, and
`check-wheel-alignment.py` reads the ELF program headers of every library in a
wheel and reports any PT_LOAD segment below 16 KB.

The build itself works. `NUMPY_NOBLAS=1` is the right setting here rather than a
fallback: the analysis has no `dot`, `matmul` or `linalg` anywhere — only
element-wise work, medians and percentiles, none of which go through BLAS. It
also sidesteps `chaquopy-openblas`, which is not installable from the upstream
index.

## Where it stopped

Every attempt to raise the alignment failed, and the same is true of matplotlib:

| | arm64-v8a | x86_64 |
|---|---|---|
| numpy (upstream) | 16 KB | 4 KB (OpenBLAS) |
| numpy (built here) | — | 4 KB |
| matplotlib (built here) | 16 KB | 4 KB |

matplotlib's script passes no alignment flags at all, and its arm64 wheel comes
out correct. That is the finding: **16 KB alignment is a toolchain default for
arm64 and only for arm64** — the one Android ABI where devices use 16 KB pages.
For x86_64 it exists on emulator images and nowhere else, so the toolchain does
not aim for it.

Three ways of asking for it anyway were tried, none of which changed the result:

- `LDFLAGS` exported in the shell — meson ignores the host's flags when cross
  compiling
- `[built-in options] c_link_args` in a meson cross file — meson-python appends
  its own cross file after any given one, and the later wins
- `setup-args=-Dc_link_args=…` on the command line, plus the flag appended to
  `LDFLAGS` through `CIBW_ENVIRONMENT_ANDROID` so it comes last

## What is done instead

The emulator runs a **4 KB** x86_64 image — any API level image whose name does
not say "16 KB page size". `adb shell getconf PAGE_SIZE` says which one is
running. That tests the app rather than the page size.

16 KB pages only occur on arm64, which is what real devices use and what the
released app is tested on. There every library is correctly aligned, upstream
numpy included.

## What is worth keeping

`check-wheel-alignment.py` found this in seconds and would have found the
original 16 KB problem months earlier. If the wheels are ever rebuilt, running it
afterwards costs nothing:

```bash
python3 poc/android-x86_64-16k/check-wheel-alignment.py android/app/wheels/*.whl
```

Alongside that, `android/app/build.gradle.kts` installs the matplotlib wheel by
**file name**, which hands the arm64 wheel to every ABI. That does not matter
while only arm64 wheels are kept, but it is why a second wheel in the folder
would not be picked up. Installing by name and version instead lets pip choose by
platform tag.
