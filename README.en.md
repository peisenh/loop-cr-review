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

The same CamAPS stream can also sit in **Nightscout** (`entries` / `treatments`). That dump is recognised and stays in **lite** mode by default: the assessment rests on the glucose course alone and the loop figures stay empty. They are added only with `--assume-camaps` or the upload checkbox.

## ⚠️ Supported systems — CamAPS FX only

> **This tool is developed and tested exclusively for CamAPS FX (Auto Mode).**

The core method relies on CamAPS delivering auto-corrections as **modulated basal**. Extra basal in the meal window is additional Auto Mode activity; it *may* fit a too-weak/too-strong CR, but on real CamAPS it is not specific to that. Other systems work differently:

- **Tandem Control-IQ, Omnipod 5, and others** deliver auto-corrections partly as **boluses**. These do not appear in the basal → the loop extra basal underestimates the compensation, and the verdict is distorted.
- **Nightscout:** `entries.json` + `treatments.json` dump (API, no live fetch). CGM from `sgv`, meals from Meal/Correction Bolus, basal from `Temp Basal`. Times: UTC from the ISO string, local clock via the CGM `utcOffset` (treatment offset 0 is ignored). **Default is lite** — Part 2 only with `--assume-camaps`, and only if this really is CamAPS via NS. Do not treat AAPS/Loop Nightscout as CamAPS.
- **LibreView:** one glucose CSV (record types 0/4/5). Always lite — no basal, so no loop figures.
- **Dexcom Clarity:** the CSV from the Clarity export (`EGV`/`Carbs`/`Insulin` rows).
  Carbs and insulin only as far as they were logged in the Dexcom app; long-acting
  insulin does not count as a meal bolus. Always lite — no basal, so no loop figures.

**What lite sources show.** Without a basal trace only the loop figures drop out — loop extra
basal, `CR_eff` and the fasting basal rate. Everything the glucose curve alone can say stays:
the return Δ4h, the per-slot CR assessment that follows from it, stability and spread, and all
derivations from the curve shape. What remains is the classic view — this much bolus for this
many carbs, and this is where glucose stood four hours later. With no loop smoothing the
excursion that signal is arguably more direct than under CamAPS.


Use with other loops is **conceivable with adaptations**, but untested — in particular, (1) the export columns would need to be mapped and (2) auto-correction **boluses** would need to be included in the "loop extra basal" term. Without these adaptations, the results are not valid for non-CamAPS systems.

## The core idea

Under CamAPS FX Auto Mode the algorithm often changes **basal** after a meal. Glucose may still return to baseline — a return test alone then says little. The report also shows extra basal delivered in the meal window:

```
loop extra basal = ∫ (basal rate − fasting basal) dt   over the window after the meal
CR_eff           = CHO / (meal bolus + loop extra basal)
```

Positive loop extra basal may fit a too-weak CR, but on CamAPS it is not specific to that.

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

Four ways to run it — pick one: the **command line** (1), the **homelab web
front-end** (2), the **desktop app** (3), or the **Android app** (4).

### 1 · Command line

```bash
# unpack the Glooko export, then:
python3 loop_cr_review.py <export_folder>            # default: 4-h window
python3 loop_cr_review.py .                          # export sits in the current folder
python3 loop_cr_review.py <export_folder> -w 3.5     # different window (hours)
python3 loop_cr_review.py <export_folder> --lang en  # report in English (default: de)
python3 loop_cr_review.py <ns-folder>                # Nightscout: entries.json + treatments.json → lite
python3 loop_cr_review.py <ns-folder> --assume-camaps  # NS: enable CamAPS Part 2
python3 loop_cr_review.py <libreview-folder>          # LibreView CSV → always lite
python3 loop_cr_review.py <clarity-folder>            # Dexcom Clarity CSV → always lite
python3 loop_cr_review.py <export_folder> --span      # print from–to only
python3 loop_cr_review.py <export_folder> --from 2026-08-01 --to 2026-08-14
python3 loop_cr_review.py <export_folder> -o report.html
python3 loop_cr_review.py <export_folder> -t <template_folder>
```

| Option | Meaning | Default |
| --- | --- | --- |
| `export_dir` | Folder with a Glooko export, Nightscout dump, LibreView or Clarity CSV. **Required**; searched up to two levels below | — |
| `-w, --window-hours` | postprandial analysis window (h) | `4.0` |
| `--dark-charts` | also render dark-theme chart PNGs (AGP, slot curves, baseline-norm, and daily with `-d`); without this, only light charts | off |
| `--assume-camaps` | Loop figures (loop extra basal, CR_eff) for Nightscout as well. LibreView and Clarity stay lite. Default off | off |
| `--span` | print the CGM date range, no report | off |
| `--from` / `--to` | calendar days YYYY-MM-DD (inclusive) | full export |
| `-d, --daily` | also output a daily overview (small day profiles per calendar day) | off |
| `--slots-profile` | `default` · `extended` (05–11/11–15/15–22) · `with_snacks` (snacks 09–11 and 15–17) | `default` |
| `--slots-file` | custom time-of-day slots from JSON (see `example-data/slots.example.json`); overrides the profile | — |
| `--lang` | report language (`de` or `en`) | `de` |
| `-o, --out` | output HTML | `<name>_loop-cr-review_<window>.html` |
| `-t, --template-dir` | folder containing `report.html.j2` | `./templates` |

**PDF:** open the report in a browser → Print → "Save as PDF" (cards are protected against page breaks).

Prebuilt CLI binaries (`loop-cr-review-linux` ~50–60 MB, `loop-cr-review-windows.exe`
~30–40 MB) are attached to each release and need no Python. They are unsigned — see
the first-start note under [3 · Desktop app](#3--desktop-app-double-click).

### 2 · Web front-end (homelab)

A small Flask app offers the same analysis in the browser: Glooko ZIP, Nightscout
ZIP (`entries.json` + `treatments.json`), or LibreView CSV. After choosing the
file the full date range is filled in, then the report. Those are separate
requests. While a report is being built the upload and the result sit in a
private folder under the system temp directory. The export is deleted as soon as
the report exists; the report itself after 15 minutes at the latest, or right
away with "download". The report is shown in a chrome (New report / Save);
the saved HTML is the same file the CLI writes. Nightscout stays lite unless you tick
“force CamAPS assessment”. Meant for **private LAN use, not public hosting**.

```bash
# with Docker (recommended)
cp docker-compose.example.yml docker-compose.yml   # adjust if needed
docker compose up --build                          # http://<homelab-ip>:8000

# or without Docker
pip install -r requirements.txt -r requirements-web.txt
python3 webapp.py                                  # http://127.0.0.1:8000
```

The form exposes the same options as the CLI — language, meal window, daily
overview — plus a download switch and the time-of-day slots (built-in profiles, custom fields, or JSON), which can be left
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

### 4 · Android (sideload)

The same analysis in an APK, no server. Releases attach
`loop-cr-review-android.apk`. Install from the file manager (allow unknown
sources). **Not a Play Store build.**

**Works on:** devices that boot **4 KB memory pages** — Pixel 8/9/10 (16 KB
developer option off), Lenovo Tab M11, most current phones. Built and run on
a Pixel 8 (Android 17) and a Tab M11.

**Does not work on:** a kernel with **16 KB pages** (16 KB emulator image,
Pixel “Boot with 16KB page size”, future devices that default to 16 KB).
Chaquopy’s numpy/matplotlib wheels are 4 KB-aligned; there is no matplotlib
wheel built against numpy 2 to take instead. That is also why this APK cannot
go to Play (`targetSdk` 35 requires 16 KB-capable native libs).

Build locally (JDK 17 + Android SDK):

```bash
./tools/build-android-apk.sh
# → dist/loop-cr-review-android.apk
```

Project: `android/`. How it got there: `docs/android-poc.md`.

Everything stays on the device; nothing is sent off it.


## Privacy & homelab (short)

> Not legal advice — technical notes for **self-hosted** use only.

- **CLI and desktop app:** analysis runs only on your machine; the export and HTML report stay local. The tool does not upload data to any network service.
- **Web front-end:** intended for a **private home network**, not the public internet. Uploads are written to a temporary directory and deleted as soon as the report has been built from them; the report follows within a quarter of an hour. There is deliberately no persistence and no analysis logging of file contents.
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

**Nightscout** — folder or ZIP with:

- `entries.json` — CGM (`sgv`, `dateString` / `date`, `utcOffset`)
- `treatments.json` — `Meal Bolus` / `Correction Bolus` / `Temp Basal` (`created_at`, `carbs`, `insulin`, `rate`/`absolute`, `duration`)

From your own site, e.g. `/api/v1/entries.json?count=100000` and `/api/v1/treatments.json?count=100000` (do not put the token in the tool). Lite unless you pass `--assume-camaps`.

**LibreView** — a `*glucose*.csv` from libreview.com (German or English headers). Historic glucose (type 0) plus carbs/insulin (types 5/4). Always lite.

## Project structure

```
loop-cr-review/
├── loop_cr_review.py          # logic (reading, analysis, charts, context) + CLI
├── webapp.py                  # optional homelab web front-end (Flask)
├── gui.py                     # desktop app (pywebview + local server)
├── templates/
│   ├── report.html.j2         # presentation (Jinja2) — adjust layout/wording here
│   ├── upload.html.j2         # web front-end upload form
│   └── viewer.html.j2         # chrome around the report (New report / Save)
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
├── tools/                     # binaries, screenshots, Android APK, validation
├── android/                   # Android app (sideload, 4 KB devices)
├── poc/browser-pyodide/       # Browser experiment (not the app path)
├── VALIDATION.md              # measured reliability of spread/stability
├── sim/
│   ├── SIMULATION-SPEC.md     # method-validation spec (Phase A/B, frozen)
│   ├── PHASE_B_DESIGN.md
│   ├── PHASE_B_ROBUST.md
│   └── UPTAKE.md              # results and conclusion
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
