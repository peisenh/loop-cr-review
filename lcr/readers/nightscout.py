# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading a Nightscout export (entries + treatments as JSON or CSV)."""
import json
from collections import Counter
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


def _ns_parse_time(obj, fallback_min):
    """UTC instant from dateString/created_at/date, then naive local time.

    The offset comes from the record itself where it has one, and only from
    *fallback_min* where it does not. Taking one offset for the whole export
    was wrong across a daylight-saving change: a six-month range starting in
    March carried the winter offset into every summer day, and every reading
    came out an hour early.
    """
    raw = obj.get("dateString") or obj.get("created_at")
    if raw:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    elif obj.get("date"):
        dt = datetime.fromtimestamp(float(obj["date"]) / 1000.0, tz=timezone.utc)
    else:
        return None
    off = _ns_record_offset(obj)
    if off is None:
        off = int(fallback_min or 0)
    local = dt.astimezone(timezone(timedelta(minutes=off)))
    return local.replace(tzinfo=None)


def _ns_record_offset(obj):
    """The record's own offset in minutes, or None if it has none. -> int|None

    Zero counts as no offset. Uploaders that do not track the wearer's time
    write it, and reading it as Greenwich would move those records by the
    whole offset — where a record genuinely was taken at UTC, the fallback
    lands on the same value anyway.
    """
    raw = obj.get("utcOffset")
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value or None


def _ns_offset_minutes(entries):
    """Offset for records that carry none. -> int

    The most common one in the export, not the first: the first record is the
    oldest, and in a range that crosses a daylight-saving change that is the
    wrong side of it.
    """
    offs = [off for off in (_ns_record_offset(x) for x in entries) if off is not None]
    if not offs:
        return 0
    return Counter(offs).most_common(1)[0][0]


def read_nightscout(base):
    """Load a Nightscout dump (entries.json + treatments.json).

    Times: ISO Z / epoch as UTC, then shifted to each record's own ``utcOffset``
    so slot clocks match the wearer. A record without one — Nightscout writes a
    zero where the uploader does not track the zone — takes the offset most of
    the export carries.
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
