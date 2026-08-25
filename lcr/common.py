# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared foundation: i18n, units, errors, method constants, small helpers.

Imported by every other module; imports none of them, so there are no cycles.
"""
import gettext as _gettext_module
import json
import subprocess
import sys
import warnings
from collections import defaultdict
from contextlib import contextmanager
import contextvars
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

__all__ = [
    "tool_version",
    "sorted_unique_series",
    "merge_carb_entries",
    "_basal_from_segments",
    "DAILY_BOLUS_Y",
    "DAILY_CARB_Y",
    "DAILY_ROW",
    "DAILY_MIN_GAP",

    "resource_dir",
    "N_",
    "LoopCRError",
    "_TRANSLATION",
    "_",
    "setup_i18n",
    "current_translation",
    "DEFAULT_SLOTS",
    "SLOT_PROFILES",
    "_SLOT_PALETTE",
    "slots_from_profile",
    "_derive_slot_globals",
    "_SLOTS_VAR",
    "_default_slot_state",
    "_slot_state",
    "_slot_scope",
    "MEAL_MIN_CHO",
    "MERGE_SEC",
    "MIN_CLEAN_MEALS",
    "BOOTSTRAP_N",
    "BOOTSTRAP_SEED",
    "MIN_MEALS_FOR_STABILITY",
    "MIN_DAYS_FOR_STABILITY",
    "FEW_DAYS_HINT",
    "STABILITY_HIGH",
    "STABILITY_MODERATE",
    "MAX_GAP_MIN",
    "build_slots",
    "load_slots_file",
    "FASTING_HOURS",
    "REST_EXCL_AFTER_MEAL_MIN",
    "REST_MIN_WINDOW_MIN",
    "REST_MIN_WINDOWS",
    "REST_MIN_HOURS",
    "REST_REL",
    "REST_OFF_FRAC",
    "LOOP_RATIO",
    "D4_WEAK",
    "D4_STRONG",
    "D4_HIGH",
    "CR_DEV_LOW",
    "CR_DEV_HIGH",
    "PRE_BG_HIGH",
    "PEAK_EARLY",
    "PEAK_RISE_HIGH",
    "NADIR_LOW",
    "NADIR_LATE",
    "HYPO_BG",
    "MGDL_PER_MMOL",
    "_GLUCOSE_UNIT",
    "set_glucose_unit",
    "glucose_unit",
    "is_mmol",
    "g",
    "fmt_glucose",
    "fmt_delta",
    "TIME_FMTS",
    "TOOL_NAME",
    "REPO_URL",
    "num",
    "parse_ts",
    "fmt_cr",
    "slot_of",
    "_slot_norm_rows",
    "WEEKDAYS",
    "select_slot_rows",
    "slot_median_curve",
    "slot_norm_curve",
    "slot_norm_bands",
]


def resource_dir():
    """Base directory for bundled files (template).

    As a PyInstaller binary the data lives in sys._MEIPASS, otherwise next to this module.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", "."))
    # This module lives in lcr/, the bundled data next to the repository root.
    return Path(__file__).resolve().parents[1]

# --- i18n -------------------------------------------------------------------
# gettext-based localisation. Source strings (msgids) are English; the German
# and English catalogs live under locale/<lang>/LC_MESSAGES/messages.mo.
# Active language is stored in a ContextVar so concurrent callers (threaded
# waitress/gunicorn) do not leak translations across requests.


def N_(message):
    """Mark a string for extraction without translating it yet (gettext_noop).

    Used for strings defined at import time (e.g. slot labels) that must be
    translated later, once the catalog is loaded.
    """
    return message


class LoopCRError(Exception):
    """User-facing analysis / input error (bad export, invalid slots, ...).

    Front-ends catch this and map it to CLI exit codes or HTTP 400.
    Replaces former ``sys.exit(...)`` calls inside the analysis core so the
    library API does not terminate the host process.
    """


_TRANSLATION = contextvars.ContextVar(
    "loop_cr_translation", default=_gettext_module.NullTranslations())


def _(message):
    """Translate ``message`` using the active (context-local) catalog.

    Falls back to the English msgid when no catalog is installed yet.
    """
    return _TRANSLATION.get().gettext(message)


def setup_i18n(lang):
    """Install the gettext translation for ``lang`` (e.g. 'de', 'en').

    The catalog is stored in a ContextVar so concurrent report generations
    with different languages do not overwrite each other. Falls back to a
    no-op translator (msgid == msgstr) if no catalog is found.
    """
    localedir = resource_dir() / "locale"
    try:
        trans = _gettext_module.translation("messages", localedir=str(localedir),
                                            languages=[lang])
    except FileNotFoundError:
        trans = _gettext_module.NullTranslations()
    _TRANSLATION.set(trans)
    return trans


def current_translation():
    """Return the active (context-local) gettext translation catalog.

    Public accessor for front-ends (e.g. the web UI) that need to install the
    same catalog into their own template environment after calling
    :func:`setup_i18n`.
    """
    return _TRANSLATION.get()


# --- Method parameters (data-independent) ----------------------------------
# Built-in default slots (immutable template). Runtime analysis uses the module
# globals SLOTS / _slot_state()[1] / _slot_state()[2] / _slot_state()[3], which are installed for
# the duration of generate_report() via _slot_scope() and then restored so
# concurrent callers (e.g. threaded waitress in gui.py) do not leak custom slots.
DEFAULT_SLOTS = (
    ("breakfast", N_("Breakfast"), 5, 10),
    ("lunch", N_("Lunch"), 11, 15),
    ("dinner", N_("Dinner"), 17, 22),
    ("other", N_("Other"), -1, -1),
)
# Named profiles for CLI --slots-profile and the web dropdown (default unchanged).
# Each entry is a full slots tuple including exactly one catch-all (start=-1).
SLOT_PROFILES = {
    "default": DEFAULT_SLOTS,
    "extended": (
        ("breakfast", N_("Breakfast"), 5, 11),
        ("lunch", N_("Lunch"), 11, 15),
        ("dinner", N_("Dinner"), 15, 22),
        ("other", N_("Other"), -1, -1),
    ),
    "with_snacks": (
        ("breakfast", N_("Breakfast"), 5, 9),
        ("snack_am", N_("Morning snack"), 9, 11),
        ("lunch", N_("Lunch"), 11, 15),
        ("snack_pm", N_("Afternoon snack"), 15, 17),
        ("dinner", N_("Dinner"), 17, 22),
        ("other", N_("Other"), -1, -1),
    ),
}
_SLOT_PALETTE = ("#c0392b", "#e0913a", "#3a9b46", "#2c6fbb", "#8e44ad", "#16a085")


def slots_from_profile(name):
    """Return a copy of a built-in slot profile, or raise LoopCRError."""
    if name not in SLOT_PROFILES:
        known = ", ".join(sorted(SLOT_PROFILES))
        raise LoopCRError(f"Unknown slots profile {name!r} (known: {known}).")
    return list(SLOT_PROFILES[name])


def _derive_slot_globals(slots):
    """Derive _slot_state()[1]/_slot_state()[2]/_slot_state()[3] from a SLOTS list.

    "other"-like catch-all entries (start < 0) stay out;
    all other slots automatically land in _slot_state()[1] and get a
    colour assigned from the palette.
    """
    main_slots = tuple(k for k, _lab, start, _end in slots if start >= 0)
    label = {k: _(lab) for k, lab, _start, _end in slots}
    color = {k: _SLOT_PALETTE[i % len(_SLOT_PALETTE)] for i, k in enumerate(main_slots)}
    return main_slots, label, color


# Slot tables are context-local (ContextVar) so concurrent generate_report()
# calls do not leak custom slots into each other. Accessors below keep call
# sites readable; _slot_scope() installs a call-specific state.
_SLOTS_VAR = contextvars.ContextVar("loop_cr_slots", default=None)


def _default_slot_state():
    """Built-in DEFAULT_SLOTS plus derived main/label/color tables."""
    slots = list(DEFAULT_SLOTS)
    return (slots, *_derive_slot_globals(slots))


def _slot_state():
    """Active (slots, main_slots, labels, colors) for this context."""
    state = _SLOTS_VAR.get()
    if state is None:
        state = _default_slot_state()
        _SLOTS_VAR.set(state)
    return state


@contextmanager
def _slot_scope(slots):
    """Install ``slots`` (or the built-in defaults) for the duration of the body.

    State lives in a ContextVar (not process globals) so concurrent callers
    (threaded waitress/gunicorn) cannot leak custom slots into each other.
    Labels are re-derived after ``setup_i18n`` so gettext is applied.
    """
    slot_list = list(slots) if slots is not None else list(DEFAULT_SLOTS)
    state = (slot_list, *_derive_slot_globals(slot_list))
    token = _SLOTS_VAR.set(state)
    try:
        yield
    finally:
        _SLOTS_VAR.reset(token)


MEAL_MIN_CHO = 20          # g, lower bound for a "real" meal
MERGE_SEC = 45 * 60        # Boli innerhalb dieser Spanne zusammenfassen
MIN_CLEAN_MEALS = 3        # prefer contamination-free meals; else fall back to all
# Decision stability (bootstrap): how often the slot verdict survives resampling
# whole days of meals. Coverage of the spread is driven by the number of *days*,
# not of meals: measured against a known median it reaches ~90 % from 5 days
# (79 % at 3 days, 85 % at 4), so that is where the gate sits. Below it the card
# falls back to the plainly observed range. Seed is fixed so a report stays
# reproducible; the bands are heuristic and labelled as such.
BOOTSTRAP_N = 2000
BOOTSTRAP_SEED = 20260817
MIN_MEALS_FOR_STABILITY = 5
MIN_DAYS_FOR_STABILITY = 5
# Below this many days a correctly set slot is still flagged fairly often
# (measured: 34 % at 5 days, 24 % at 7, 13 % at 10 — see VALIDATION.md).
FEW_DAYS_HINT = 10
STABILITY_HIGH = 90.0      # >= high, >= STABILITY_MODERATE moderate, else low
STABILITY_MODERATE = 75.0
MAX_GAP_MIN = 25           # CGM gap (minutes) inside the post-meal window → cgm_gap flag


def build_slots(raw, source="Slots"):
    """Validate a parsed slots list -> [(key, label, start, end), ...].

    Shared by :func:`load_slots_file` and other front-ends (e.g. the web
    form, which builds the list from input fields). ``source`` is only used
    in error messages. Order = priority (first match wins); exactly one
    catch-all entry with start=-1/end=-1 is required. Aborts with a clear
    message as LoopCRError instead of silently using wrong slots.
    """
    if not isinstance(raw, list) or not raw:
        raise LoopCRError(f"{source}: expected a non-empty list of slot objects.")
    slots, seen_keys, catchall = [], set(), 0
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise LoopCRError(f"{source}, entry {i}: expected an object (key/label/start/end).")
        missing = [f for f in ("key", "label", "start", "end") if f not in entry]
        if missing:
            raise LoopCRError(f"{source}, entry {i}: missing fields {missing}.")
        key, label, start, end = entry["key"], entry["label"], entry["start"], entry["end"]
        if key in seen_keys:
            raise LoopCRError(f"{source}: duplicate key '{key}'.")
        seen_keys.add(key)
        if (not isinstance(start, int) or not isinstance(end, int)
                or isinstance(start, bool) or isinstance(end, bool)):
            raise LoopCRError(f"{source}, '{key}': start/end must be a whole number.")
        if start == -1 and end == -1:
            catchall += 1
        elif not (0 <= start < 24 and 0 < end <= 24 and start < end):
            raise LoopCRError(f"{source}, '{key}': start/end must satisfy 0<=start<end<=24 "
                              "(or both -1 for the catch-all slot).")
        slots.append((key, label, start, end))
    if catchall != 1:
        raise LoopCRError(f"{source}: exactly one catch-all entry (start=-1, end=-1) "
                          f"required, found: {catchall}.")
    return slots


def load_slots_file(path):
    """Load custom slot time windows from a JSON file (list of objects).

    Expected: [{"key": "...", "label": "...", "start": H, "end": H}, ...].
    Validation is delegated to :func:`build_slots`.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LoopCRError(f"Slots file '{path}' unreadable/not valid JSON: {exc}") from exc
    return build_slots(raw, f"Slots file '{path}'")
FASTING_HOURS = (0, 1, 2, 3, 4, 5)
# Meal-free rest vs fasting basal (context, not a CR estimate).
REST_EXCL_AFTER_MEAL_MIN = 180   # minutes after a meal start are not "rest"
REST_MIN_WINDOW_MIN = 120        # shortest usable meal-free stretch
REST_MIN_WINDOWS = 3
REST_MIN_HOURS = 6
REST_REL = 0.20                  # |mean rate / fasting − 1|
REST_OFF_FRAC = 0.30             # share of minutes that far off
LOOP_RATIO = 0.12          # |loop extra basal / bolus| notable from here
D4_WEAK, D4_STRONG = 15, -30
D4_HIGH = 40               # Δ4h clearly too high from here (even without loop signal)
CR_DEV_LOW, CR_DEV_HIGH = 0.75, 1.33
PRE_BG_HIGH = 150
# Thresholds for the curve-shape derivations
PEAK_EARLY = 75            # min: peak before this time counts as "early"
PEAK_RISE_HIGH = 55        # mg/dL rise above start: "high peak"
NADIR_LOW = 85             # mg/dL: nadir below this = notable
NADIR_LATE = 120           # min: nadir after this time = late (insulin tail)
HYPO_BG = 70               # mg/dL: glucose below this = hypo (rescue-carb context)

# --- glucose unit -----------------------------------------------------------
# All glucose thresholds above are defined in mg/dL. Exports come in either
# mg/dL or mmol/L (detected from the CGM column header). The whole report is
# then rendered in the export's unit: g() converts an mg/dL threshold into the
# active unit, so metrics, chart bands and axes all stay consistent.
MGDL_PER_MMOL = 18.0182
# Active glucose unit is context-local so concurrent report generations
# (e.g. one mg/dL and one mmol/L request) do not overwrite each other.
_GLUCOSE_UNIT = contextvars.ContextVar("loop_cr_glucose_unit", default="mg/dL")


def set_glucose_unit(unit):
    """Set the active glucose unit ('mg/dL' or 'mmol/L') for this report call."""
    _GLUCOSE_UNIT.set(unit)


def glucose_unit():
    """Return the active glucose unit for this report call."""
    return _GLUCOSE_UNIT.get()


def is_mmol():
    """True if the active glucose unit is mmol/L."""
    return glucose_unit() == "mmol/L"


def g(mgdl):
    """Convert an mg/dL glucose value/threshold to the active unit.

    mmol/L is rounded to 1 decimal (the resolution CGM reports use); mg/dL is
    returned unchanged as an int-like float.
    """
    return round(mgdl / MGDL_PER_MMOL, 1) if is_mmol() else mgdl


def fmt_glucose(value):
    """Format a glucose value already in the active unit: 1 decimal for mmol/L,
    integer for mg/dL."""
    return f"{value:.1f}" if is_mmol() else f"{value:.0f}"


def fmt_delta(value):
    """Format a glucose *difference* in the active unit (signed): 1 decimal for
    mmol/L, integer for mg/dL."""
    return f"{value:+.1f}" if is_mmol() else f"{value:+.0f}"

TIME_FMTS = ("%d.%m.%Y %H:%M",    # de:    29.07.2026 09:02
             "%d/%m/%Y %H:%M",    # en/UK: 29/07/2026 09:02
             "%d-%m-%Y %H:%M",    # LibreView: 21-08-2026 16:24
             "%Y-%m-%d %H:%M",    # en_US/ISO: 2026-07-29 09:02
             "%Y-%m-%dT%H:%M:%S",  # Dexcom Clarity: 2026-07-29T09:02:31
             "%Y-%m-%d %H:%M:%S")  # same, some exports use a space
TOOL_NAME = "Loop-CR-Review"
REPO_URL = "https://github.com/peisenh/loop-cr-review"


# --- small helpers ----------------------------------------------------------
def num(val):
    """Parse a number from the export -> float; empty -> nan.

    Handles both decimal separators used across export locales: comma (de,
    '5,4') and dot (en, '5.4'). No thousands separators occur in these exports
    (all values are small), so a comma is unambiguously the decimal mark.
    """
    val = val.strip().strip('"')
    if val == "":
        return np.nan
    parsed = float(val.replace(",", ".")) if "," in val else float(val)
    return parsed if np.isfinite(parsed) else np.nan


def parse_ts(val):
    """Timestamp from the export to datetime."""
    for fmt in TIME_FMTS:
        try:
            return datetime.strptime(val.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Unknown time format: {val!r}")


def fmt_cr(value):
    """Carb ratio as '1:x.x' or '—' for nan."""
    return f"1:{value:.1f}" if value and not np.isnan(value) else "—"


def slot_of(hour):
    """Time-of-day slot for an hour."""
    for key, _lab, start, end in _slot_state()[0]:
        if 0 <= start <= hour < end:
            return key
    # catch-all: the slot with start < 0 (only one is allowed, see load_slots_file)
    return next(key for key, _lab, start, _end in _slot_state()[0] if start < 0)


def _slot_norm_rows(meals, slot, window, val_at, clean_times=None):
    """Baseline-normalised per-meal rows for a slot. Empty list if none."""
    grid = np.arange(0, window + 1, 10)
    rows = []
    for m in meals:
        if slot_of(m["time"].hour) != slot:
            continue
        if clean_times is not None and m["time"] not in clean_times:
            continue
        row = np.array([val_at(m["time"], int(g), 6) for g in grid], dtype=float)
        if np.isnan(row[0]):
            continue
        rows.append(row - row[0])
    return rows, grid


WEEKDAYS = (N_("Monday"), N_("Tuesday"), N_("Wednesday"), N_("Thursday"),
            N_("Friday"), N_("Saturday"), N_("Sunday"))


# --- slot selection and curves (used by both analysis and charts) ------
def select_slot_rows(slot_rows):
    """Single definition of which meals feed a slot's table/verdict/norm-curve.

    Preference: contamination-free rows without a large CGM gap in the window
    (``contam`` and ``cgm_gap`` both False). If fewer than
    :data:`MIN_CLEAN_MEALS` such rows exist, fall back to **all** rows for that
    slot (F1) so a sparse export still yields a median. Returns
    ``(used_rows, n_clean, used_clean_only)`` where ``n_clean`` counts
    contamination-free rows (gap flag does not reduce that display count).

    Note: the *absolute* median postprandial curve (:func:`slot_median_curve`)
    still uses every meal in the slot (no contamination/gap filter). Only the
    Δ-oriented table aggregation and the baseline-normalised curves share this
    selector — changing the absolute curve would alter shape captions and
    lever metrics.
    """
    n_clean = sum(1 for r in slot_rows if not r["contam"])
    preferred = [r for r in slot_rows
                 if not r["contam"] and not r.get("cgm_gap")]
    if len(preferred) >= MIN_CLEAN_MEALS:
        return preferred, n_clean, True
    return list(slot_rows), n_clean, False

def slot_median_curve(meals, slot, window, val_at):
    """Median postprandial curve (0..window) of a slot or None."""
    grid = np.arange(0, window + 1, 10)
    stacks = [[val_at(m["time"], int(g), 6) for g in grid]
              for m in meals if slot_of(m["time"].hour) == slot]
    return np.nanmedian(np.array(stacks), axis=0) if stacks else None

def slot_norm_curve(meals, slot, window, val_at, clean_times=None):
    """Baseline-normalised median curve of a slot (start of each meal = 0).

    Each individual meal is referenced to its own baseline at t=0,
    THEN the median is taken. This shows the typical course
    RELATIVE to the meal start -- unlike the absolute median curve, whose
    start and end are aggregated independently and can swallow a real net drop
    (Δ4h).

    clean_times: optional set of meal start times. If provided,
    ONLY these meals are used -- so the curve uses the same
    (contamination-cleaned) data basis as the Δ4h column of the table and
    cannot contradict it. Meals without a baseline value (no CGM at t=0)
    are additionally dropped. Returns: (curve or None, n meals used).
    """
    rows, _grid = _slot_norm_rows(meals, slot, window, val_at, clean_times)
    if not rows:
        return None, 0
    return np.nanmedian(np.array(rows), axis=0), len(rows)

def slot_norm_bands(meals, slot, window, val_at, clean_times=None):
    """Median + percentile bands of baseline-normalised curves for one slot.

    Returns None or dict with grid, n, p10, p25, p50, p75, p90.
    """
    rows, grid = _slot_norm_rows(meals, slot, window, val_at, clean_times)
    if not rows:
        return None
    arr = np.array(rows, dtype=float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return {
            "grid": grid, "n": len(rows),
            "p10": np.nanpercentile(arr, 10, axis=0),
            "p25": np.nanpercentile(arr, 25, axis=0),
            "p50": np.nanpercentile(arr, 50, axis=0),
            "p75": np.nanpercentile(arr, 75, axis=0),
            "p90": np.nanpercentile(arr, 90, axis=0),
        }

# Layout of the daily panels (y positions of the event rows).
DAILY_BOLUS_Y, DAILY_CARB_Y, DAILY_ROW, DAILY_MIN_GAP = 452, 388, 18, 0.9


def _basal_from_segments(segs):
    """Paint (start, duration_min, rate) segments -> same tuple as read_basal_timeline."""
    if not segs:
        raise LoopCRError("No basal rates found.")
    segs = sorted(segs)
    t0 = segs[0][0]
    minutes = int((segs[-1][0] + timedelta(minutes=segs[-1][1]) - t0).total_seconds() // 60) + 1
    minutes = max(minutes, 1)
    rate = np.full(minutes, np.nan)
    for start, dur, value in segs:
        i0 = int((start - t0).total_seconds() // 60)
        if i0 >= minutes or i0 + max(int(dur), 1) <= 0:
            continue
        a = max(0, i0)
        b = min(minutes, i0 + max(int(dur), 1))
        rate[a:b] = value
    last = segs[0][2]
    for i in range(minutes):
        if np.isnan(rate[i]):
            rate[i] = last
        else:
            last = rate[i]
    fasting_idx = [i for i in range(minutes)
                   if (t0 + timedelta(minutes=i)).hour in FASTING_HOURS]
    fasting = float(np.mean([rate[i] for i in fasting_idx])) if fasting_idx else float(np.mean(rate))
    per_night = defaultdict(list)
    for i in fasting_idx:
        per_night[(t0 + timedelta(minutes=i)).date()].append(rate[i])
    night_means = [float(np.mean(v)) for v in per_night.values() if v]
    fb_lo = fb_hi = fasting
    fb_spread = False
    if night_means:
        fb_lo, fb_hi = min(night_means), max(night_means)
        fb_spread = (fb_hi - fb_lo) >= 0.3
    return rate, t0, minutes, fasting, fb_lo, fb_hi, fb_spread

def merge_carb_entries(raw):
    """Carb entries -> (meals, minors), merged and split by size.

    Entries closer than MERGE_SEC belong to one meal (split boluses, corrections
    keyed in separately). Identical for every source, so it lives here rather
    than three times over.
    """
    raw.sort(key=lambda m: m["time"])
    merged = []
    for meal in raw:
        if merged and (meal["time"] - merged[-1]["time"]).total_seconds() <= MERGE_SEC:
            merged[-1]["cho"] += meal["cho"]
            merged[-1]["bolus"] += meal["bolus"]
            if "bg" in meal and "bg" in merged[-1]:
                # Glooko carries a pre-meal reading per entry; keep the higher one.
                merged[-1]["bg"] = max(merged[-1]["bg"], meal["bg"])
        else:
            merged.append(dict(meal))
    meals = [m for m in merged if m["cho"] >= MEAL_MIN_CHO and m["bolus"] > 0]
    minors = [m for m in merged if m["cho"] < MEAL_MIN_CHO or m["bolus"] <= 0]
    return meals, minors

def sorted_unique_series(times, gluc):
    """CGM samples -> arrays sorted by time, duplicate timestamps dropped.

    Sources deliver rows in file order and can repeat a timestamp; the
    analysis assumes a strictly increasing series.
    """
    times = np.array(times)
    gluc = np.array(gluc)
    order = np.argsort(times, kind="stable")
    times, gluc = times[order], gluc[order]
    keep = np.concatenate(([True], times[1:] != times[:-1]))
    return times[keep], gluc[keep]


def tool_version():
    """Version for the header, or "" if not determinable.

    Order: 1) _version.py resolved via 'git archive'/export-subst (source zip)
    2) _version.py pre-filled by CI (binary)  3) 'git describe' in the checkout
    4) nothing -> caller then hides the version string.
    """
    try:
        from _version import VERSION            # pylint: disable=import-outside-toplevel
        if VERSION and "$Format" not in VERSION:
            return VERSION.strip()
    except ImportError:
        pass
    if not getattr(sys, "frozen", False):
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--dirty", "--always"],
                cwd=resource_dir(), capture_output=True, text=True, timeout=2, check=True)
            if result.stdout.strip():
                return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return ""
