# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading a LibreView CSV export. Always lite: it carries no basal rate."""
import csv
from pathlib import Path

import numpy as np

from lcr.common import (
    LoopCRError, merge_carb_entries, num, parse_ts, set_glucose_unit, sorted_unique_series)



def libreview_csv(base):
    """First CSV that looks like a LibreView glucose export, or None."""
    for path in sorted(Path(base).rglob("*.csv")):
        try:
            with open(path, encoding="utf-8-sig", newline="") as fh:
                first = fh.readline()
                second = fh.readline()
        except (OSError, UnicodeDecodeError):
            continue
        blob = (first + " " + second).lower()
        if "aufzeichnungstyp" in blob or "record type" in blob:
            return path
    return None


def is_libreview(base):
    """True when the directory holds a LibreView export."""
    return libreview_csv(base) is not None


def read_libreview(base):
    """LibreView CSV → same dict as read_nightscout. Always lite (no basal).

    Record types: 0 historic CGM, 1 scan (fallback), 4 rapid insulin, 5 carbs.
    """
    path = libreview_csv(base)
    if path is None:
        raise LoopCRError("No LibreView CSV found.")
    with open(path, encoding="utf-8-sig", newline="") as fh:
        meta = next(fh)
        reader = csv.reader(fh)
        header = next(reader)
        head = [h.strip().lower() for h in header]

        def col(*names):
            for name in names:
                if name.lower() in head:
                    return head.index(name.lower())
            return None

        i_dev = col("Gerät", "Device")
        i_ts = col("Gerätezeitstempel", "Device Timestamp")
        i_typ = col("Aufzeichnungstyp", "Record Type")
        i_hist = col("Glukosewert-Verlauf mg/dL", "Historic Glucose mg/dL",
                     "Glukosewert-Verlauf mmol/L", "Historic Glucose mmol/L")
        i_scan = col("Glukose-Scan mg/dL", "Scan Glucose mg/dL",
                     "Glukose-Scan mmol/L", "Scan Glucose mmol/L")
        i_cho = col("Kohlenhydrate (Gramm)", "Carbohydrates (grams)")
        i_ins = col("Schnellwirkendes Insulin (Einheiten)",
                    "Rapid-Acting Insulin (units)")
        i_meal_ins = col("Mahlzeiteninsulin (Einheiten)", "Meal Insulin (units)")
        i_corr = col("Korrekturinsulin (Einheiten)", "Correction Insulin (units)")
        if i_ts is None or i_typ is None:
            raise LoopCRError("LibreView CSV is missing timestamp or record type.")
        gluc_hdr = " ".join(
            header[i] for i in (i_hist, i_scan) if i is not None).lower()
        set_glucose_unit("mmol/L" if "mmol" in gluc_hdr else "mg/dL")
        name = "LibreView"
        for key in ("Erstellt von", "Created by"):
            if key in meta:
                # meta is a csv line: ...,Erstellt von,Name
                parts = [x.strip() for x in meta.split(",")]
                if key in parts:
                    j = parts.index(key)
                    if j + 1 < len(parts) and parts[j + 1]:
                        name = parts[j + 1]
        times, gluc, sensor = [], [], "LibreView"
        raw = []
        for row in reader:
            if len(row) <= i_typ:
                continue
            typ = row[i_typ].strip()
            try:
                ts = parse_ts(row[i_ts])
            except (ValueError, IndexError):
                continue
            if i_dev is not None and row[i_dev].strip():
                sensor = row[i_dev].strip()
            if typ == "0" and i_hist is not None and i_hist < len(row) and row[i_hist].strip():
                times.append(ts)
                gluc.append(num(row[i_hist]))
            cho = num(row[i_cho]) if i_cho is not None and i_cho < len(row) else np.nan
            ins = 0.0
            for idx in (i_ins, i_meal_ins, i_corr):
                if idx is not None and idx < len(row) and row[idx].strip():
                    v = num(row[idx])
                    if not np.isnan(v):
                        ins += v
            if (not np.isnan(cho) and cho > 0) or ins > 0:
                raw.append({"time": ts, "cho": 0.0 if np.isnan(cho) else cho, "bg": np.nan,
                            "bolus": ins})
    if not times:
        raise LoopCRError("LibreView CSV has no glucose rows.")
    times, gluc = sorted_unique_series(times, gluc)
    meals, minors = merge_carb_entries(raw)
    events = [{"time": m["time"], "cho": m["cho"], "bolus": m["bolus"]} for m in meals + minors]
    return {
        "times": times, "gluc": gluc, "name": name, "sensor": sensor,
        "meals": meals, "minors": minors, "pump": "LibreView",
        "basal": None, "events": events, "tdd": {}, "source": "libreview",
    }
