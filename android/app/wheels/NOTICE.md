# Third-party code in the Android APK

Loop CR review itself is AGPL-3.0 (`LICENSE` at the repository root).
Everything listed below keeps **its own** license. Bundling in the APK
does not place those components under AGPL.

The numpy wheel is downloaded at APK build time from
<https://chaquo.com/pypi-upstream/>. Other Python packages are resolved by
Chaquopy from PyPI / ChaQuo's public index. License texts also ship inside the
APK as each package's `*.dist-info` metadata.

## Committed / fetched binary wheels

| Package | Artifact | License | Text |
|---------|----------|---------|------|
| numpy | `2.3.2-1`, CPython 3.13, `android_24_arm64_v8a` | BSD-3-Clause | [licenses/LICENSE-numpy](licenses/LICENSE-numpy) |


## Also in the APK (not committed here)

| Component | License |
|-----------|---------|
| CPython (Chaquopy runtime) | PSF |
| Chaquopy | MIT |
| AndroidX (`core-ktx`) | Apache-2.0 |
| Flask, Jinja2, Werkzeug, click, itsdangerous, MarkupSafe | BSD-3-Clause |
| blinker | MIT |
| waitress | ZPL-2.1 |

Project source: <https://github.com/peisenh/loop-cr-review>
