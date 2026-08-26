# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading a Dexcom Clarity CSV export. Always lite: it carries no basal rate.

One row per event, all in the same file: glucose readings (`EGV`), carbs,
insulin, exercise, plus a handful of device and alert-setting rows at the top.
Carbs and insulin only appear when they were logged in the Dexcom app, so an
export may well be glucose only — the report then shows what it can.
"""
import csv

import numpy as np

from lcr.common import (
    HEAD_BYTES, LoopCRError, merge_carb_entries, num, parse_ts, set_glucose_unit,
    single_match, sniff_candidates, sorted_unique_series)

# Rows before the data: FirstName/LastName/Device carry the patient and device,
# Alert rows are threshold settings and of no interest here.
META_TYPES = {"FirstName", "LastName", "Device", "Alert"}
# Below 40 and above 400 the sensor reports words instead of a number. Using the
# limit keeps the row in the series; dropping it would look like a sensor gap.
LIMIT_VALUES = {"low": 40.0, "high": 400.0}


def dexcom_csv(base):
    """The CSV that looks like a Dexcom Clarity export, or None."""
    hits = []
    for path in sniff_candidates(base, "*.csv", "CSV files"):
        try:
            with open(path, encoding="utf-8-sig", newline="") as handle:
                header = handle.read(HEAD_BYTES).lower()
        except (OSError, UnicodeDecodeError):
            continue
        if "event type" in header and "transmitter time" in header:
            hits.append(path)
    return single_match(hits, "Dexcom Clarity CSVs", base)


def is_dexcom(base):
    """True when the directory holds a Dexcom Clarity export."""
    return dexcom_csv(base) is not None


def _glucose(raw, unit_is_mmol):
    """Glucose cell -> value. 'Low'/'High' become the limit they stand for."""
    text = raw.strip()
    if not text:
        return np.nan
    limit = LIMIT_VALUES.get(text.lower())
    if limit is not None:
        return limit / 18.0 if unit_is_mmol else limit
    return num(text)


def read_dexcom(base):
    """Dexcom Clarity CSV → same dict as the other readers. Always lite."""
    path = dexcom_csv(base)
    if path is None:
        raise LoopCRError("No Dexcom Clarity CSV found.")

    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        head = {(k or "").strip().lower(): (k or "") for k in (reader.fieldnames or [])}

        def col(*needles):
            for needle in needles:
                for low, original in head.items():
                    if needle in low:
                        return original
            return None

        c_ts, c_type = col("timestamp"), col("event type")
        c_sub, c_gluc = col("event subtype"), col("glucose value")
        c_ins, c_cho = col("insulin value"), col("carb value")
        c_info, c_device = col("patient info"), col("device info")
        if c_ts is None or c_type is None or c_gluc is None:
            raise LoopCRError("Dexcom CSV is missing timestamp, event type or glucose column.")

        # The unit is part of the column name, not of the values.
        unit_is_mmol = "mmol" in c_gluc.lower()
        set_glucose_unit("mmol/L" if unit_is_mmol else "mg/dL")

        times, gluc, raw = [], [], []
        first, last, sensor = "", "", "Dexcom"
        for row in reader:
            kind = (row.get(c_type) or "").strip()
            if kind in META_TYPES:
                # Name and device live in these rows; everything else is settings.
                value = (row.get(c_info) or "").strip()
                if kind == "FirstName":
                    first = value
                elif kind == "LastName":
                    last = value
                elif kind == "Device" and c_device and (row.get(c_device) or "").strip():
                    sensor = row[c_device].strip()
                continue
            try:
                stamp = parse_ts(row.get(c_ts) or "")
            except (ValueError, TypeError):
                continue

            if kind == "EGV":
                value = _glucose(row.get(c_gluc) or "", unit_is_mmol)
                if not np.isnan(value):
                    times.append(stamp)
                    gluc.append(value)
                continue

            cho = num(row.get(c_cho) or "") if c_cho else np.nan
            bolus = 0.0
            if kind == "Insulin" and c_ins:
                # Long-acting is the basal substitute on injections — it says
                # nothing about a single meal, so only fast-acting counts here.
                if (row.get(c_sub) or "").strip().lower().startswith("fast"):
                    value = num(row[c_ins])
                    bolus = 0.0 if np.isnan(value) else value
            if kind == "Carbs" and (np.isnan(cho) or cho <= 0):
                continue
            if (kind == "Carbs" and cho > 0) or bolus > 0:
                raw.append({"time": stamp, "cho": 0.0 if np.isnan(cho) else cho,
                            "bg": np.nan, "bolus": bolus})

    if not times:
        raise LoopCRError("Dexcom CSV has no glucose rows.")
    times, gluc = sorted_unique_series(times, gluc)
    meals, minors = merge_carb_entries(raw)
    events = [{"time": m["time"], "cho": m["cho"], "bolus": m["bolus"]} for m in meals + minors]
    name = " ".join(part for part in (first, last) if part) or "Dexcom"
    return {
        "times": times, "gluc": gluc, "name": name, "sensor": sensor,
        "meals": meals, "minors": minors, "pump": "Dexcom Clarity",
        "basal": None, "events": events, "tdd": {}, "source": "dexcom",
    }
