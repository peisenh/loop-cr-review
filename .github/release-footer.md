
---

⚠️ **Not a medical device — analysis only.** No diagnosis, no treatment recommendation.
Never change insulin/CR settings without your treating diabetes care team. No warranty.

Prebuilt programs are attached below under **Assets**:

- **Command line** — `loop-cr-review-linux` (~50–60 MB), `loop-cr-review-windows.exe` (~30–40 MB)
  Self-contained, no Python and no dependencies: download, make executable, run
  against an unpacked export folder.

- **Desktop app** (native window, no browser tab) — same analysis as the web UI:

  | Asset | Size | For | Notes |
  |-------|------|-----|--------|
  | `loop-cr-review-gui-windows.exe` | ~35–45 MB | **Windows 10 / 11** (recommended) | Slim. Uses **Edge WebView2** (usually already installed on Win10/11). Prefer this on current systems. |
  | `loop-cr-review-gui-windows-qt.exe` | ~245–255 MB | **Older Windows** or no WebView2 | Full **Qt WebEngine** bundled. Larger; use if the slim build fails or WebView2 is missing (e.g. some older/LTSC images). |
  | `loop-cr-review-gui-linux` | ~275–285 MB | **Linux** | Qt WebEngine bundled (large). |

**Windows: the binaries are not code-signed.** SmartScreen will warn on first start
("Windows protected your PC"). If you trust the source, choose **More info →
Run anyway**. Alternatively check the SHA-256 shown next to each asset, or run
from source instead (see README).

**Linux:** make it executable first — `chmod +x loop-cr-review-gui-linux`.

**Android (sideload)** — `loop-cr-review-android.apk`
  Same analysis on the phone, all on-device. Release-signed with the same
  key as local builds. Install from the file manager (unknown sources).
  Play Protect may ask once. Uninstall 0.20.x first — different signature.

  The APK carries no compiled code: charts as SVG, arithmetic in plain
  Python. Alignment and ABI no longer arise.

  Third-party: Flask, Jinja2 and waitress, all pure Python. Project code is
  AGPL-3.0. Texts: `android/NOTICE.md` in the source repo.

All variants run entirely on your machine; your data never leaves it.
