# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading a Nightscout export (entries + treatments as JSON or CSV)."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


from lcr import pure
from lcr.common import (
    LoopCRError, _basal_from_segments, find_below, merge_carb_entries, set_glucose_unit,
    single_match, sorted_unique_series)


def is_nightscout(base):
    """True if this folder (or a child) is a Nightscout entries+treatments dump."""
    return _nightscout_dir(base) is not None


def _nightscout_dir(base):
    """The folder holding entries.json + treatments.json, or None."""
    base = Path(base)
    cands = [c for c in (base, *(p.parent for p in find_below(base, "entries.json")))
             if (c / "entries.json").is_file() and (c / "treatments.json").is_file()]
    return single_match(dict.fromkeys(cands), "Nightscout dumps", base)


def _ns_parse_time(obj, offset_min):
    """UTC instant from dateString/created_at/date, then naive local via offset_min."""
    raw = obj.get("dateString") or obj.get("created_at")
    if raw:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    elif obj.get("date"):
        dt = datetime.fromtimestamp(float(obj["date"]) / 1000.0, tz=timezone.utc)
    else:
        return None
    off = int(offset_min or 0)
    local = dt.astimezone(timezone(timedelta(minutes=off)))
    return local.replace(tzinfo=None)


def _ns_offset_minutes(entries):
    """Display offset from CGM entries (Nightscout utcOffset is minutes)."""
    offs = [int(x["utcOffset"]) for x in entries if x.get("utcOffset") not in (None, "")]
    return offs[0] if offs else 0


def read_nightscout(base):
    """Load a Nightscout dump (entries.json + treatments.json).

    Times: ISO Z / epoch as UTC, then shifted to the CGM ``utcOffset`` so slot
    clocks match the wearer. Treatment ``utcOffset: 0`` is ignored.
    """
    ns = _nightscout_dir(base)
    if ns is None:
        raise LoopCRError("No Nightscout entries.json + treatments.json found.")
    entries = json.loads((ns / "entries.json").read_text(encoding="utf-8-sig"))
    treatments = json.loads((ns / "treatments.json").read_text(encoding="utf-8-sig"))
    if not isinstance(entries, list) or not isinstance(treatments, list):
        raise LoopCRError("Nightscout JSON must be arrays.")
    offset = _ns_offset_minutes(entries)
    set_glucose_unit("mg/dL")
    times, gluc = [], []
    for row in entries:
        if row.get("type") not in (None, "sgv"):
            continue
        sgv = row.get("sgv")
        if sgv is None:
            continue
        ts = _ns_parse_time(row, offset)
        if ts is None:
            continue
        times.append(ts)
        gluc.append(float(sgv))
    if not times:
        raise LoopCRError("Nightscout entries.json has no sgv rows.")
    times, gluc = sorted_unique_series(times, gluc)
    raw = []
    for row in treatments:
        ts = _ns_parse_time(row, offset)
        if ts is None:
            continue
        cho = float(row["carbs"]) if row.get("carbs") not in (None, "") else 0.0
        ins = float(row["insulin"]) if row.get("insulin") not in (None, "") else 0.0
        if cho > 0 or ins > 0:
            raw.append({"time": ts, "cho": cho, "bg": pure.NAN, "bolus": ins})
    meals, minors = merge_carb_entries(raw)
    segs = []
    for row in treatments:
        if row.get("eventType") not in ("Temp Basal", "Temporary Basal"):
            continue
        ts = _ns_parse_time(row, offset)
        if ts is None:
            continue
        rate = row.get("rate")
        if rate is None:
            rate = row.get("absolute")
        if rate is None:
            continue
        dur = row.get("duration") or 5
        segs.append((ts, max(int(round(float(dur))), 1), float(rate)))
    basal = _basal_from_segments(segs) if segs else None
    events = []
    for row in treatments:
        ts = _ns_parse_time(row, offset)
        if ts is None:
            continue
        cho = float(row["carbs"]) if row.get("carbs") not in (None, "") else 0.0
        ins = float(row["insulin"]) if row.get("insulin") not in (None, "") else 0.0
        if cho > 0 or ins > 0:
            events.append({"time": ts, "cho": cho, "bolus": ins})
    return {
        "times": times, "gluc": gluc, "name": "Nightscout",
        "sensor": "Nightscout", "meals": meals, "minors": minors,
        "pump": "Nightscout", "basal": basal, "events": events, "tdd": {},
        "source": "nightscout",
    }
