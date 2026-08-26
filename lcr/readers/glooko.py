# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading a Glooko/CamAPS export: CGM, meals, boluses, basal segments, daily totals."""
import csv
import re
from pathlib import Path

import numpy as np

from lcr.common import (
    LoopCRError, _basal_from_segments, merge_carb_entries, num, parse_ts, set_glucose_unit)


def is_glooko(base):
    """True when the folder holds Glooko's cgm_data_*.csv. Name only, no reading."""
    return bool(numbered_csvs(base, "cgm_data"))


def numbered_csvs(directory, stem):
    """All numbered export files <stem>_N.csv, sorted numerically.

    Glooko zerlegt grosse Exporte in cgm_data_1.csv, cgm_data_2.csv, ...
    """
    files = list(Path(directory).glob(f"{stem}_*.csv"))

    def order(path):
        match = re.search(rf"{re.escape(stem)}_(\d+)\.csv$", path.name)
        return int(match.group(1)) if match else 0

    return sorted(files, key=order)


def read_cgm(base):
    """-> (times[np.array], glucose[np.array], patient_name, sensor).

    Reads all cgm_data_*.csv (Glooko splits long periods across several files).
    """
    times, gluc, sensor, name = [], [], "", "Patient"
    files = numbered_csvs(base, "cgm_data")
    if not files:
        raise FileNotFoundError(f"No cgm_data_*.csv found in {base}")
    for idx, path in enumerate(files):
        with open(path, encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            meta = next(reader)
            header = next(reader)
            if idx == 0:
                match = re.search(r"Name\s*:\s*([^,]+)", ",".join(meta))
                if match:
                    name = match.group(1).strip()
                # unit from the glucose column header, e.g. "... (mmol/l)" / "(mg/dl)"
                set_glucose_unit("mmol/L" if "mmol" in ",".join(header).lower()
                                 else "mg/dL")
            for row in reader:
                if len(row) >= 2 and row[1].strip():
                    times.append(parse_ts(row[0]))
                    gluc.append(num(row[1]))
                    if not sensor and len(row) >= 3 and row[2].strip():
                        sensor = row[2].strip()
    times = np.array(times)
    gluc = np.array(gluc)
    order = np.argsort(times, kind="stable")
    times, gluc = times[order], gluc[order]
    if len(times):                                   # Duplikate (gleicher Zeitstempel) raus
        keep = np.concatenate(([True], times[1:] != times[:-1]))
        times, gluc = times[keep], gluc[keep]
    return times, gluc, name, sensor


def read_meals(base):
    """-> (meals, minors, pump).

    meals  = merged carb entries >= MEAL_MIN_CHO g with a bolus (the analysed meals).
    minors = merged carb entries below that bar (small snacks / hypo rescues); kept
             so analyze_meals() can flag contamination and hypo rescues that would
             otherwise be invisible.
    """
    raw, pump = [], ""
    for path in numbered_csvs(base / "Insulin data", "bolus_data"):
        with open(path, encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            next(reader)
            next(reader)
            for row in reader:
                if not pump and len(row) >= 9 and row[8].strip():
                    pump = row[8].strip()
                if len(row) < 6:
                    continue
                cho = num(row[3])
                if not np.isnan(cho) and cho > 0:
                    ins = num(row[5])
                    raw.append({"time": parse_ts(row[0]), "cho": cho, "bg": num(row[2]),
                                "bolus": 0.0 if np.isnan(ins) else ins})
    meals, minors = merge_carb_entries(raw)
    return meals, minors, pump


def read_tdd(base):
    """Daily insulin totals from insulin_data_*.csv: {date: (bolus, total, basal)} or {}."""
    out = {}
    for path in numbered_csvs(base / "Insulin data", "insulin_data"):
        with open(path, encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            next(reader)
            next(reader)
            for row in reader:
                if len(row) >= 4 and row[0].strip():
                    bolus, total, basal = num(row[1]), num(row[2]), num(row[3])
                    if not np.isnan(total):
                        out[parse_ts(row[0]).date()] = (bolus, total, basal)
    return out


def read_bolus_events(base):
    """All individual bolus/carb entries (unmerged) for the daily overview."""
    events = []
    for path in numbered_csvs(base / "Insulin data", "bolus_data"):
        with open(path, encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            next(reader)
            next(reader)
            for row in reader:
                if len(row) < 6:
                    continue
                cho, ins = num(row[3]), num(row[5])
                cho = 0.0 if np.isnan(cho) else cho
                ins = 0.0 if np.isnan(ins) else ins
                if cho > 0 or ins > 0:
                    events.append({"time": parse_ts(row[0]), "cho": cho, "bolus": ins})
    return events


def read_basal_timeline(base):
    """-> (rate[np.array U/h per minute], t0, minutes, fasting_basal)."""
    segs = []
    for path in numbered_csvs(base / "Insulin data", "basal_data"):
        with open(path, encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            next(reader)
            next(reader)
            for row in reader:
                if len(row) < 5:
                    continue
                rate_val = num(row[4])
                if not np.isnan(rate_val):
                    dur = num(row[2])
                    segs.append((parse_ts(row[0]), int(dur) if not np.isnan(dur) else 5, rate_val))
    if not segs:
        raise LoopCRError(f"No basal rates found in {base / 'Insulin data'} "
                          "(basal_data_*.csv empty or missing).")
    return _basal_from_segments(segs)
