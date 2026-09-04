# Third-party code in the Android APK

Loop CR review itself is AGPL-3.0 (`LICENSE` at the repository root).
Everything listed below keeps **its own** license. Bundling in the APK does not
place those components under AGPL.

## Python packages

None of them is compiled. Chaquopy resolves them from PyPI at build time, and
each ships its own license inside the APK as `*.dist-info` metadata.

| Package | License |
|---------|---------|
| Flask | BSD-3-Clause |
| Jinja2 | BSD-3-Clause |
| waitress | ZPL-2.1 |
| MarkupSafe, Werkzeug, itsdangerous, click, blinker (Flask dependencies) | BSD-3-Clause |

## Runtime and toolchain

| Component | License |
|-----------|---------|
| CPython (bundled by Chaquopy) | PSF-2.0 |
| Chaquopy runtime | MIT |
| AndroidX libraries | Apache-2.0 |

Until this release the APK also carried **numpy** and a hand-built **matplotlib**
wheel. Both are gone: the charts are drawn as SVG and the arithmetic is plain
Python, so nothing in the app is compiled. What that involved is recorded in
[`../poc/svg-charts/`](../poc/svg-charts/) and
[`../poc/matplotlib-android-wheel/`](../poc/matplotlib-android-wheel/).
