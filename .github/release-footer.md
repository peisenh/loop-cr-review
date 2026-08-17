
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

All variants run entirely on your machine; your data never leaves it.
