# Third-party code in the Android APK

Loop CR review itself is AGPL-3.0 (`LICENSE` at the repository root).
Everything listed below keeps **its own** license. Bundling in the APK
does not place those components under AGPL.

This directory commits the **matplotlib** Android wheel. **numpy** is
downloaded at APK build time from
<https://chaquo.com/pypi-upstream/> (the version matplotlib was built
against). Other Python packages are resolved by Chaquopy from PyPI /
ChaQuo’s public index. License texts also ship inside the APK as each
package’s `*.dist-info` metadata.

## Committed / fetched binary wheels

| Package | Artifact | License | Text |
|---------|----------|---------|------|
| numpy | `2.3.2-1`, CPython 3.13, `android_24_arm64_v8a` | BSD-3-Clause | [licenses/LICENSE-numpy](licenses/LICENSE-numpy) |
| matplotlib | `matplotlib-*-cp313-cp313-android_24_arm64_v8a.whl` (ELF align `0x4000`) | Matplotlib license (PSF-based) plus bundled fonts/libs | [licenses/LICENSE-matplotlib](licenses/LICENSE-matplotlib); full tree: <https://github.com/matplotlib/matplotlib/tree/v3.9.0/LICENSE> |

Copyright remains with the NumPy developers and the Matplotlib Development
Team. Rebuild matplotlib with `./tools/build-matplotlib-android-wheel.sh`
and commit the replacement wheel (exactly one arm64 file in this directory).

## Also in the APK (not committed here)

| Component | License |
|-----------|---------|
| CPython (Chaquopy runtime) | PSF |
| Chaquopy | MIT |
| AndroidX (`core-ktx`) | Apache-2.0 |
| Flask, Jinja2, Werkzeug, click, itsdangerous, MarkupSafe | BSD-3-Clause |
| blinker | MIT |
| waitress | ZPL-2.1 |
| matplotlib dependencies (contourpy, cycler, fonttools, kiwisolver, pillow, pyparsing, python-dateutil, packaging, six) | BSD / MIT / HPND-PIL / Apache-2.0 as upstream |

Project source: <https://github.com/peisenh/loop-cr-review>
