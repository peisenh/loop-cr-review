# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading exports: one module per source, plus what they share.

A new data source is a new file here, not more lines in an existing one.
Everything is re-exported from the package, so callers do not need to know
which source a reader belongs to — and the analysis does not care which one
produced the structures it gets.

    glooko.py      Glooko/CamAPS CSV export (the only source with basal)
    nightscout.py  Nightscout JSON dumps
    libreview.py   LibreView CSV (always lite: no basal)
    dexcom.py      Dexcom Clarity CSV (always lite: no basal)
"""
import csv
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from lcr.readers.glooko import (
    numbered_csvs, read_basal_timeline, read_bolus_events, read_cgm, read_meals,
    read_tdd)
from lcr.readers.dexcom import dexcom_csv, is_dexcom, read_dexcom
from lcr.readers.libreview import is_libreview, libreview_csv, read_libreview
from lcr.readers.nightscout import (
    _nightscout_dir, _ns_offset_minutes, _ns_parse_time, is_nightscout,
    read_nightscout)

__all__ = [
    "dexcom_csv",
    "is_dexcom",
    "read_dexcom",
    "_nightscout_dir",
    "_ns_offset_minutes",
    "_ns_parse_time",
    "clip_by_days",
    "is_libreview",
    "is_nightscout",
    "libreview_csv",
    "numbered_csvs",
    "parse_day",
    "peek_span",
    "read_basal_timeline",
    "read_bolus_events",
    "read_cgm",
    "read_libreview",
    "read_meals",
    "read_nightscout",
    "read_tdd",
]

from lcr.common import (

    FASTING_HOURS, LoopCRError, MEAL_MIN_CHO, MERGE_SEC, REST_EXCL_AFTER_MEAL_MIN,
    REST_MIN_HOURS, REST_MIN_WINDOWS, REST_MIN_WINDOW_MIN, REST_OFF_FRAC, REST_REL, num,
    parse_ts, resource_dir, set_glucose_unit)



# --- Reading ----------------------------------------------------------------





















def parse_day(value):
    """YYYY-MM-DD -> date, or None if empty."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise LoopCRError(f"invalid date {value!r} (use YYYY-MM-DD)") from exc


def peek_span(base):
    """Source + CGM calendar span without building a report.

    Does not keep anything; caller owns the folder. Meals/basal are not required.
    """
    base = Path(base)
    if is_nightscout(base):
        data = read_nightscout(base)
        times, source = data["times"], "nightscout"
    elif is_libreview(base):
        data = read_libreview(base)
        times, source = data["times"], "libreview"
    else:
        times, _gluc, _n, _s = read_cgm(base)
        source = "glooko"
    if times is None or len(times) == 0:
        raise LoopCRError("no CGM timestamps in this export")
    d0, d1 = times[0].date(), times[-1].date()
    days = (d1 - d0).days + 1
    return {
        "source": source,
        "from": d0.isoformat(),
        "to": d1.isoformat(),
        "days": days,
    }


def clip_by_days(times, gluc, meals, minors, events, date_from, date_to, window_min):
    """Keep meals on [from, to] inclusive; CGM until to + window (last-meal Δ)."""
    if date_from is None and date_to is None:
        return times, gluc, meals, minors, events
    if times is None or len(times) == 0:
        raise LoopCRError("no CGM data to clip")
    d0 = date_from or times[0].date()
    d1 = date_to or times[-1].date()
    if d0 > d1:
        raise LoopCRError("from date is after to date")
    t_lo = datetime.combine(d0, datetime.min.time())
    t_meal_hi = datetime.combine(d1, datetime.min.time()) + timedelta(days=1)
    t_cgm_hi = t_meal_hi + timedelta(minutes=int(window_min))
    mask = np.array([(t_lo <= ts < t_cgm_hi) for ts in times])
    if not mask.any():
        raise LoopCRError("no CGM samples in the chosen date range")
    times, gluc = times[mask], gluc[mask]
    def keep(items):
        if not items:
            return items
        return [m for m in items if t_lo <= m["time"] < t_meal_hi]
    return times, gluc, keep(meals), keep(minors), keep(events)
