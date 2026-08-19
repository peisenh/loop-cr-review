<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo-readme-dark.svg">
    <img alt="loop-cr-review" src="docs/logo-readme-light.svg" width="440">
  </picture>
</h1>

[🇩🇪 Deutsch](README.md) · **🇬🇧 English**

**Loop-aware Carb-Ratio Review** — carb-ratio assessment from real CamAPS FX data.

**CamAPS FX (Auto Mode) only.** Other AID systems are not supported — see “Supported systems”.

Analyses a CamAPS/Glooko export and produces a self-contained HTML report with an Ambulatory Glucose Profile (AGP), consensus metrics, and a **loop-aware assessment of carbohydrate ratios (CR)** per time-of-day slot.

![Example report from loop-cr-review](docs/screenshot.png)

*Example report with synthetic demo data ([full report](docs/screenshot_full.png)).*

---

## ⚠️ Important notice — please read first

> **This is not a medical device and is intended solely for analysis.**
>
> - The tool **does not provide a diagnosis** and **no treatment recommendation**. It merely performs a statistical analysis of already-existing CGM and pump data.
> - The results are intended **solely as a basis for discussion with your diabetes care team**.
> - **Never change insulin, CR, correction, or any other therapy settings without consulting and obtaining approval from your treating diabetes care team.**
> - There is **no warranty** as to accuracy, completeness, or fitness for a particular purpose. Use at your own risk.
> - Under hybrid closed loop (CamAPS FX Auto Mode), the analyses are **confounded** by the ongoing loop compensation and algorithm adaptation — they are indications, not proof.

---

## What it does

- **AGP** (percentiles 5/25/50/75/95 over 24 h) and **median postprandial curves** per slot.
- **Consensus metrics** (Battelino 2019): mean glucose, GMI, CV, TIR/TITR/TBR/TAR, sensor wear.
- **Loop-aware CR assessment** per slot (breakfast / lunch / dinner) with a data-driven verdict (too weak / too strong / adequate) and a per-meal detail table.
- **Derivations from the curve shape**: per slot, curve metrics (peak height/time, nadir, late rise) and, derived from them, candidate levers (bolus-meal interval, dose, fat/protein, hypo caution) — as hypotheses for the care team, plus a clarification of `CR_eff` as an approach rather than a target value.
- Everything patient-related (name, device, period, interpretation) is drawn **from the data**; nothing is hard-coded.

## Context: CamAPS FX & Glooko

**CamAPS FX** is an app (CamDiab) implementing the Cambridge hybrid closed-loop algorithm (MPC). It **modulates basal insulin delivery** continuously (raising / lowering / suspending, roughly every 8–12 min) to keep glucose in the target range; **meal boluses** are entered by the user, calculated via the carbohydrate ratio (CR). It is combined with CGM sensors (e.g. FreeStyle Libre 3, Dexcom) and compatible pumps (e.g. YpsoPump). "Auto Mode" denotes the closed control loop.

**Glooko** is a diabetes data platform. CamAPS uploads CGM, bolus, and basal data there; from there you export a data ZIP with the CSV files this tool reads.

**Data flow:** CamAPS FX (Auto Mode) → Glooko → CSV export (ZIP) → `loop-cr-review` → HTML report. So "Glooko/CamAPS export" refers to the ZIP file with CamAPS data downloaded from Glooko.

## ⚠️ Supported systems — CamAPS FX only

> **This tool is developed and tested exclusively for CamAPS FX (Auto Mode).**

The core method relies on CamAPS delivering auto-corrections as **modulated basal**. The loop's extra basal within the meal window is therefore the signal for a too-weak/too-strong CR. Other systems work differently:

- **Tandem Control-IQ, Omnipod 5, and others** deliver auto-corrections partly as **boluses**. These do not appear in the basal → the loop extra basal underestimates the compensation, and the verdict is distorted.
- **AndroidAPS, Loop/Trio** have their own export/data structures (e.g. Nightscout instead of Glooko).

Use with other loops is **conceivable with adaptations**, but untested — in particular, (1) the export columns would need to be mapped and (2) auto-correction **boluses** would need to be included in the "loop extra basal" term. Without these adaptations, the results are not valid for non-CamAPS systems.

## The core idea

Under CamAPS FX Auto Mode, the algorithm corrects a too-weak CR via **increased basal**. Blood glucose then still returns to baseline — the classic postprandial-return test *misses* the too-weak CR. The actual signal is therefore **not** the glucose curve, but the basal additionally delivered by the loop within the meal window:

```
loop extra basal = ∫ (basal rate − fasting basal) dt   over the window after the meal
CR_eff           = CHO / (meal bolus + loop extra basal)
```

Positive loop extra basal ⇒ the loop is compensating for a too-weak CR ⇒ `CR_eff` is tighter than the derived CR. The return Δ then serves only as confirmation.

## Installation

Debian/Ubuntu via system packages (recommended, e.g. in a homelab):

```bash
sudo apt install python3-numpy python3-matplotlib python3-jinja2
```

Or platform-independently via pip (in a venv if desired):

```bash
pip install -r requirements.txt
```

### Prebuilt binaries (no Python)

For each release, self-contained executables are built via GitHub Actions and attached
(`loop-cr-review-linux`, `loop-cr-review-windows.exe`) — download, make executable, done.
The report template is bundled inside the binary.

Build it yourself (on the respective platform, no cross-compile):

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --name loop-cr-review \
  --add-data "templates/report.html.j2:templates" loop_cr_review.py   # Windows: ";" instead of ":"
```

## Usage

Three ways to run it — pick one: the **command line** (1), the **homelab web
front-end** (2), or the **desktop app** (3).

### 1 · Command line

```bash
# unpack the Glooko export, then:
python3 loop_cr_review.py <export_folder>            # default: 4-h window
python3 loop_cr_review.py <export_folder> -w 3.5     # different window (hours)
python3 loop_cr_review.py <export_folder> --lang en  # report in English (default: de)
python3 loop_cr_review.py <export_folder> -o report.html
python3 loop_cr_review.py <export_folder> -t <template_folder>
```

| Option | Meaning | Default |
| --- | --- | --- |
| `export_dir` | unpacked Glooko/CamAPS export | `.` |
| `-w, --window-hours` | postprandial analysis window (h) | `4.0` |
| `-d, --daily` | also output a daily overview (small day profiles per calendar day) | off |
| `--slots-file` | custom time-of-day slots from a JSON file (see `example-data/slots.example.json`) | built-in slots |
| `--lang` | report language (`de` or `en`) | `de` |
| `-o, --out` | output HTML | `<name>_loop-cr-review_<window>.html` |
| `-t, --template-dir` | folder containing `report.html.j2` | `./templates` |

**PDF:** open the report in a browser → Print → "Save as PDF" (cards are protected against page breaks).

Prebuilt CLI binaries (`loop-cr-review-linux` ~50–60 MB, `loop-cr-review-windows.exe`
~30–40 MB) are attached to each release and need no Python. They are unsigned — see
the first-start note under [3 · Desktop app](#3--desktop-app-double-click).

### 2 · Web front-end (homelab)

A small Flask app offers the same analysis in the browser: upload the export
ZIP, pick the options, get the report back. It is meant for **private LAN use in
a homelab, not public hosting** — health data is processed in a temporary
directory and deleted immediately (nothing is stored, nothing is logged).

```bash
# with Docker (recommended)
cp docker-compose.example.yml docker-compose.yml   # adjust if needed
docker compose up --build                          # http://<homelab-ip>:8000

# or without Docker
pip install -r requirements.txt -r requirements-web.txt
python3 webapp.py                                  # http://127.0.0.1:8000
```

The form exposes the same options as the CLI — language, meal window, daily
overview — plus a download switch and the time-of-day slots, which can be left
at the built-in default, entered in an inline field editor, or uploaded as JSON.
`docker-compose.example.yml` includes an optional, commented-out Traefik block
for HTTPS + Basic-Auth if you want a reverse proxy in front; the real
`docker-compose.yml` is gitignored so local settings stay private. The same
**not a medical device** disclaimer applies as for the CLI.

### 3 · Desktop app (double-click)

Pre-built binaries run the same front-end in a native window — no Python, no
Docker, no browser tab. Download from the release page:

- **Windows 10 / 11 (recommended):** `loop-cr-review-gui-windows.exe` (~35–45 MB)
  Slim; uses **Edge WebView2** (normally already present on Win10/11).
- **Older Windows / no WebView2:** `loop-cr-review-gui-windows-qt.exe` (~245–255 MB)
  Full **Qt WebEngine** bundled — larger, but independent of WebView2
  (e.g. if the slim build fails or WebView2 is missing).
- **Linux:** `loop-cr-review-gui-linux` (~275–285 MB, Qt WebEngine bundled)
  Make it executable once: `chmod +x loop-cr-review-gui-linux`

**First start on Windows.** The binaries are **not code-signed** (a signing
certificate is out of scope for this project), so Windows SmartScreen shows
*"Windows protected your PC"* on first launch. If you trust the source:
**More info → Run anyway**. The file may also need *Properties → Unblock* after
download. If you would rather not run an unsigned binary, verify the SHA-256
listed next to the asset on the release page, or run from source instead.

Or from source:

```bash
# Linux / Windows with Qt
pip install -r requirements-gui.txt && python3 gui.py

# Windows slim (WebView2, no Qt)
pip install -r requirements-gui-webview2.txt && python3 gui.py
```

Everything happens locally; the data never leaves your machine.


## Privacy & homelab (short)

> Not legal advice — technical notes for **self-hosted** use only.

- **CLI and desktop app:** analysis runs only on your machine; the export and HTML report stay local. The tool does not upload data to any network service.
- **Web front-end:** intended for a **private home network**, not the public internet. Uploads are written to a temporary directory and removed after the report; there is deliberately no persistence and no analysis logging of file contents.
- **Health data** (CGM/pump) is sensitive. If you make the service available to *others* (even on LAN), you are responsible for access control (trusted users only; optionally HTTPS + Basic-Auth behind Traefik as in `docker-compose.example.yml`).
- **Public hosting** (open internet, accounts, storage) is **not** the intended mode and would trigger much stricter requirements (legal basis, transparency, security measures, often a DPIA) — this project is not designed for that.
- **Imprint / privacy policy** are typically needed when offering a service *commercially* or publicly — not for personal use on your own machine. If unsure, check yourself or get professional advice.

## Example data to try it out

The [`example-data/`](example-data/) folder contains a complete, **purely synthetic**
example export (patient "Alex Beispiel", 14 days, CamAPS FX / Libre 3 / YpsoPump) — no real
patient data. This lets you test the tool without your own export:

```bash
python3 loop_cr_review.py example-data
```

For the **web front-end** (upload form), use
[`example-data/Alex_Beispiel_Glooko_export.zip`](example-data/Alex_Beispiel_Glooko_export.zip) —
a Glooko-style ZIP with only the CSV files. After `python3 webapp.py` or
`docker compose up --build`, upload that file at http://127.0.0.1:8000.

The generated report matches the screenshot above.

Your own exports are best placed under [`data/`](data/) — the contents of this folder are
excluded via `.gitignore`, so real patient data does not end up in the repo:

```bash
python3 loop_cr_review.py data/my-export
```

## Expected input

An unpacked **Glooko export with CamAPS FX data** (see "Context" above) containing:

- `cgm_data_*.csv` — CGM values (`timestamp, glucose (mg/dl), serial number`); Glooko splits long periods across several numbered files (`cgm_data_1.csv`, `cgm_data_2.csv`, …) — all are read
- `Insulin data/bolus_data_*.csv` — boluses including `carbohydrate intake (g)` and `insulin delivered (U)`
- `Insulin data/basal_data_*.csv` — basal segments (`rate`, `duration`)

The common CamAPS export formats are detected automatically: date `dd.mm.yyyy`,
`dd/mm/yyyy` or `yyyy-mm-dd`, decimal separator comma or dot. The glucose unit
(**mg/dL** or **mmol/L**) is detected from the column header; the whole report
(metrics, axes, target ranges) is then shown in the export's unit.

## Project structure

```
loop-cr-review/
├── loop_cr_review.py          # logic (reading, analysis, charts, context) + CLI
├── webapp.py                  # optional homelab web front-end (Flask)
├── gui.py                     # desktop app (pywebview + local server)
├── templates/
│   ├── report.html.j2         # presentation (Jinja2) — adjust layout/wording here
│   └── upload.html.j2         # web front-end upload form
├── static/                    # logo assets served by the web front-end
├── example-data/              # synthetic example export to try it out
├── tests/                     # regression tests (example-data)
├── data/                      # your own exports (contents excluded via .gitignore)
├── docs/                      # screenshots + logo for the README
├── Dockerfile                 # web front-end container
├── docker-compose.example.yml # copy to docker-compose.yml (gitignored)
├── requirements.txt           # CLI dependencies
├── requirements-web.txt       # extra dependencies for the web front-end
├── requirements-gui.txt       # desktop app Qt (Linux + Windows full)
├── requirements-gui-webview2.txt  # desktop app Windows slim (WebView2)
├── tools/                     # validation scripts (not part of the analysis)
├── VALIDATION.md              # measured reliability of spread/stability
├── SIMULATION-SPEC.md         # spec for the outstanding method validation
├── README.md
├── CONTRIBUTING.md
├── LICENSE
└── .pylintrc
```

## Method parameters (data-independent)

Bundled as named constants at the top of `loop_cr_review.py` and adjustable: slot time windows, minimum meal CHO, merge window, fasting window, loop-ratio and Δ thresholds, CR-deviation and pre-meal-BG thresholds. The clinical target ranges (TIR 70–180, etc.) follow the international consensus.

## Limitations

- Valid for **announced meals**; confounders (fat/protein, exercise, pre-bolus timing, split/overlapping boluses) are dampened by medians, not eliminated.
- The **fasting basal** as a reference assumes meal-/correction-free nights (00:00–06:00).
- The CR derived from `CHO/bolus` may include corrections blended in by the bolus calculator (the tool flags this when a slot deviates noticeably).
- CamAPS's adaptation over days can partly smooth out longer-standing misconfigurations.
- **Spread and decision stability** only quantify how sensitive a result is to
  which days happened to be recorded — not whether the carb ratio is right.
  How trustworthy those numbers are themselves (measured coverage, limits of
  the procedure): [VALIDATION.md](VALIDATION.md).

## Contributing

Contributions are welcome. The project uses a **DCO sign-off** (`git commit -s`); details in the bilingual [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

**GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)** — see [`LICENSE`](LICENSE). Each source file carries an `SPDX-License-Identifier`.

Copyright © 2026 Peter Eisenhauer &lt;github@peter-e.de&gt;

---

*Once more: not a medical device, no treatment recommendation, no warranty. Changes to therapy exclusively through your treating diabetes care team.*
