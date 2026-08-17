
---

⚠️ **Not a medical device — analysis only.** No diagnosis, no treatment recommendation.
Never change insulin/CR settings without your treating diabetes care team. No warranty.

Prebuilt programs are attached below under **Assets**:

- **Command line** — `loop-cr-review-linux`, `loop-cr-review-windows.exe`
  Self-contained, no Python and no dependencies: download, make executable, run
  against an unpacked export folder.

- **Desktop app** (native window, no browser tab) — same analysis as the web UI:

  | Asset | For | Notes |
  |-------|-----|--------|
  | `loop-cr-review-gui-windows.exe` | **Windows 10 / 11** (recommended) | Slim. Uses **Edge WebView2** (usually already installed on Win10/11). Prefer this on current systems. |
  | `loop-cr-review-gui-windows-qt.exe` | **Older Windows** or no WebView2 | Full **Qt WebEngine** bundled. Larger; use if the slim build fails or WebView2 is missing (e.g. some older/LTSC images). |
  | `loop-cr-review-gui-linux` | **Linux** | Qt WebEngine bundled (large). |

All variants run entirely on your machine; your data never leaves it.
