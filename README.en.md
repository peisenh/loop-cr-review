# loop-cr-review

[🇩🇪 Deutsch](README.md) · **🇬🇧 English**

**Loop-aware Carb-Ratio Review** — carb-ratio assessment from real CamAPS FX data.

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

```bash
# unpack the Glooko export, then:
python3 loop_cr_review.py <export_folder>            # default: 4-h window
python3 loop_cr_review.py <export_folder> -w 3.5     # different window (hours)
python3 loop_cr_review.py <export_folder> -o report.html
python3 loop_cr_review.py <export_folder> -t <template_folder>
```

| Option | Meaning | Default |
| --- | --- | --- |
| `export_dir` | unpacked Glooko/CamAPS export | `.` |
| `-w, --window-hours` | postprandial analysis window (h) | `4.0` |
| `-d, --daily` | also output a daily overview (small day profiles per calendar day) | off |
| `--slots-file` | custom time-of-day slots from a JSON file (see `example-data/slots.example.json`) | built-in slots |
| `-o, --out` | output HTML | `<name>_loop-cr-review_<window>.html` |
| `-t, --template-dir` | folder containing `report.html.j2` | `./templates` |

**PDF:** open the report in a browser → Print → "Save as PDF" (cards are protected against page breaks).

## Example data to try it out

The [`example-data/`](example-data/) folder contains a complete, **purely synthetic**
example export (patient "Alex Beispiel", 14 days, CamAPS FX / Libre 3 / YpsoPump) — no real
patient data. This lets you test the tool without your own export:

```bash
python3 loop_cr_review.py example-data
```

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

German number format (comma) and `dd.mm.yyyy HH:MM` are recognised. Unit: **mg/dL**.

## Project structure

```
loop-cr-review/
├── loop_cr_review.py          # logic (reading, analysis, charts, context)
├── templates/
│   └── report.html.j2         # presentation (Jinja2) — adjust layout/wording here
├── example-data/              # synthetic example export to try it out
├── data/                      # your own exports (contents excluded via .gitignore)
├── docs/                      # screenshots for the README
├── requirements.txt
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

## Contributing

Contributions are welcome. The project uses a **DCO sign-off** (`git commit -s`); details in the bilingual [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

**GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)** — see [`LICENSE`](LICENSE). Each source file carries an `SPDX-License-Identifier`.

Copyright © 2026 Peter Eisenhauer &lt;github@peter-e.de&gt;

---

*Once more: not a medical device, no treatment recommendation, no warranty. Changes to therapy exclusively through your treating diabetes care team.*
