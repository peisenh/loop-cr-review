# data/ — your own exports (not in the repo)

Storage location for your **own** unpacked Glooko/CamAPS exports.

**Privacy:** the contents of this folder are excluded via `.gitignore` — real
CGM/pump data therefore does **not** end up in the repository and is not committed.
Only this `README.md` and the `.gitignore` are versioned.

## Usage

Unpack an export ZIP here, e.g.:

```
data/
└── 2026-jul-4w/
    ├── cgm_data_1.csv
    ├── cgm_data_2.csv
    └── Insulin data/
        ├── bolus_data_1.csv
        └── basal_data_1.csv
```

Then, from the project root:

```bash
python3 loop_cr_review.py data/2026-jul-4w
```

To just try it out without your own data, there is a synthetic example export
under [`../example-data/`](../example-data/).
