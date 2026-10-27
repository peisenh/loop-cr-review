# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading a Nightscout export (entries + treatments as JSON or CSV)."""
import bisect
import json
from collections import Counter, defaultdict
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

    *fallback_min* is minutes, or a function from the UTC instant to minutes
    (see _ns_offset_lookup), for records whose offset depends on when they are.
    """
    stamp = _ns_utc_stamp(obj)
    if stamp is None:
        return None
    dt = datetime.fromtimestamp(stamp, tz=timezone.utc)
    off = _ns_record_offset(obj)
    if off is None:
        off = int((fallback_min(dt) if callable(fallback_min) else fallback_min) or 0)
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


def _ns_offset_lookup(entries):
    """Offset for a record that carries none, taken at its own time. -> callable

    Treatments carry no offset at all (Nightscout writes zero), so one value for
    the export put every treatment on one side of a daylight-saving change: a
    meal at 11:02 after the October change came out at 12:02, its boluses and
    temp basals with it. The readings do carry the wearer's offset, so a record
    without one takes the offset of the reading nearest to it in time; an
    export without any falls back to the most common one, which is zero.
    """
    marks = []
    for row in entries:
        off = _ns_record_offset(row)
        if off is None:
            continue
        stamp = _ns_utc_stamp(row)
        if stamp is not None:
            marks.append((stamp, off))
    marks.sort()
    stamps = [stamp for stamp, _off in marks]
    common = _ns_offset_minutes(entries)

    def offset_at(dt):
        if not marks:
            return common
        index = bisect.bisect_left(stamps, dt.timestamp())
        near = [i for i in (index - 1, index) if 0 <= i < len(marks)]
        return marks[min(near, key=lambda i: abs(stamps[i] - dt.timestamp()))][1]

    return offset_at


def _ns_utc_stamp(obj):
    """The record's UTC instant as epoch seconds, or None. -> float|None"""
    raw = obj.get("dateString") or obj.get("created_at")
    try:
        if raw:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        if obj.get("date"):
            return float(obj["date"]) / 1000.0
    except (TypeError, ValueError):
        return None
    return None


# What makes two treatments the same one: the kind and every amount in it.
_NS_TREATMENT_KEY = ("eventType", "carbs", "insulin", "rate", "absolute", "duration")
CLOCK_SHIFT_S = 3600


def _ns_drop_clock_copies(treatments):
    """Treatments without the copies an uploader sent again an hour off. -> list

    After the October clock change an uploader sent two days of treatments a
    second time, each one an hour later than the first copy: same kind, same
    amounts, to the second. Read as they are, every meal of those days came
    twice and the temp basals overlapped. A record is such a copy when another
    one with the same kind and amounts lies exactly an hour away and was
    uploaded before it (srvCreated; a record without one is the older upload).
    Two of the same where neither is known to be later stay, both of them.
    """
    seen = {}
    for row in treatments:
        stamp = _ns_utc_stamp(row)
        if stamp is not None:
            seen.setdefault((tuple(row.get(k) for k in _NS_TREATMENT_KEY), stamp), []).append(row)

    def uploaded(row):
        return row.get("srvCreated") or 0

    copies = set()
    for (key, stamp), rows in seen.items():
        for other_stamp in (stamp - CLOCK_SHIFT_S, stamp + CLOCK_SHIFT_S):
            for row in rows:
                if any(uploaded(row) > uploaded(other) for other in seen.get((key, other_stamp), ())):
                    copies.add(id(row))
    return [row for row in treatments if id(row) not in copies]


# An hour of basal trace before a day counts as a day at all.
MIN_BASAL_MINUTES_PER_DAY = 60


def _ns_daily_totals(basal, events):
    """Insulin per day from the basal trace and the boluses. -> {date: (bolus, total, basal)}

    Glooko ships a summary file the pump wrote; Nightscout does not, so the
    totals are added up here. The basal half is the rate trace integrated over
    each day — the same sum the loop figures already use — and the bolus half is
    what the treatments say was given.

    Only with a basal trace: a total without it would be the bolus alone under a
    name that promises everything, which is worse than saying nothing.
    """
    if basal is None:
        return {}
    rate, t0, minutes = basal[:3]
    basal_by_day, covered = defaultdict(float), defaultdict(int)
    for minute in range(minutes):
        value = rate[minute]
        if not pure.is_nan(value):
            day = (t0 + timedelta(minutes=minute)).date()
            basal_by_day[day] += value / 60.0
            covered[day] += 1
    bolus_by_day = defaultdict(float)
    for event in events:
        if event["bolus"] > 0:
            bolus_by_day[event["time"].date()] += event["bolus"]
    # A day needs real coverage to get a total. The trace ends a few minutes
    # into the day after the last segment, and that sliver would otherwise
    # appear as a day of its own with almost no insulin in it.
    return {day: (bolus_by_day.get(day, 0.0),
                  bolus_by_day.get(day, 0.0) + basal_units,
                  basal_units)
            for day, basal_units in basal_by_day.items()
            if covered[day] >= MIN_BASAL_MINUTES_PER_DAY}


def read_nightscout(base):
    """Load a Nightscout dump (entries.json + treatments.json).

    Times: ISO Z / epoch as UTC, then shifted to each record's own ``utcOffset``
    so slot clocks match the wearer. A record without one — Nightscout writes a
    zero where the uploader does not track the zone, and on every treatment —
    takes the offset of the reading nearest to it in time.
    """
    ns = _nightscout_dir(base)
    if ns is None:
        raise LoopCRError("No Nightscout entries.json + treatments.json found.")
    entries = json.loads((ns / "entries.json").read_text(encoding="utf-8-sig"))
    treatments = json.loads((ns / "treatments.json").read_text(encoding="utf-8-sig"))
    if not isinstance(entries, list) or not isinstance(treatments, list):
        raise LoopCRError("Nightscout JSON must be arrays.")
    offset = _ns_offset_lookup(entries)
    treatments = _ns_drop_clock_copies(treatments)
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
    # Nightscout knows no pump and no sensor, only the uploader that sent the
    # readings (xDrip-UiBased, share2, ...). That is the closest thing to a
    # device the export names; the header says Nightscout once, as the source.
    uploaders = Counter(row["device"] for row in entries
                        if row.get("type") in (None, "sgv") and row.get("sgv") is not None
                        and isinstance(row.get("device"), str) and row["device"].strip())
    sensor = uploaders.most_common(1)[0][0].strip() if uploaders else None
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
        "sensor": sensor, "meals": meals, "minors": minors,
        "pump": None, "basal": basal, "events": events,
        "tdd": _ns_daily_totals(basal, events),
        "source": "nightscout",
    }
