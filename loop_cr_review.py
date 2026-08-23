#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""AGP + loop-aware CR report from a CamAPS/Glooko export.

Separates logic (this module) from presentation (report_template.html.j2). Reads CGM,
bolus and basal data, computes consensus metrics plus a loop-aware CR assessment
per time-of-day slot and renders a self-contained HTML report.
"""
import argparse
import base64
import csv
import gettext as _gettext_module
import io
import json
import logging
import os
import re
import subprocess
import sys
import warnings
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import contextmanager
import contextvars

import numpy as np
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Put the font cache in a fixed location (otherwise rebuilt on every start in the
# onefile binary) and silence the "building font cache" message — set before importing matplotlib.
os.environ.setdefault("MPLCONFIGDIR", str(Path.home() / ".cache" / "loop-cr-review-mpl"))
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
import matplotlib  # noqa: E402  pylint: disable=wrong-import-position
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  pylint: disable=wrong-import-position

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
             "%Y-%m-%d %H:%M")    # en_US/ISO: 2026-07-29 09:02
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


def fig_to_b64(fig):
    """Matplotlib figure -> base64 PNG string (keeps figure facecolor for dark charts)."""
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor(),
                edgecolor="none")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


@contextmanager
def _chart_theme(dark=False):
    """Temporary matplotlib rc for light or dark embedded charts."""
    if dark:
        params = {
            "figure.facecolor": "#1c2330",
            "axes.facecolor": "#1c2330",
            "axes.edgecolor": "#8a97a8",
            "axes.labelcolor": "#e8ecf2",
            "xtick.color": "#c0c8d4",
            "ytick.color": "#c0c8d4",
            "text.color": "#e8ecf2",
            "grid.color": "#5a6b82",
            "legend.facecolor": "#243044",
            "legend.edgecolor": "#3a4556",
        }
    else:
        params = {
            "figure.facecolor": "#ffffff",
            "axes.facecolor": "#ffffff",
            "axes.edgecolor": "#1a2233",
            "axes.labelcolor": "#1a2233",
            "xtick.color": "#1a2233",
            "ytick.color": "#1a2233",
            "text.color": "#1a2233",
            "grid.color": "#b0b8c4",
            "legend.facecolor": "#ffffff",
            "legend.edgecolor": "#dde3ee",
        }
    with plt.rc_context(params):
        yield


def _chart_palette(dark=False):
    """Fill/band colours readable on light or dark chart backgrounds."""
    if dark:
        return {
            "tir": "#1e3a28", "p5": "#2a4060", "p25": "#3a6aaa", "median": "#9ec0ff",
            "bolus": "#9ec0ff", "carb": "#f0a090", "cgm": "#7eb0ff", "basal": "#6a90c0",
        }
    return {
        "tir": "#dff0df", "p5": "#bcd4ff", "p25": "#5b8def", "median": "#0b2e6b",
        "bolus": "#0b2e6b", "carb": "#c0392b", "cgm": "#0b2e6b", "basal": "#5b8def",
    }


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


# --- Reading ----------------------------------------------------------------
def resource_dir():
    """Base directory for bundled files (template).

    As a PyInstaller binary the data lives in sys._MEIPASS, otherwise next to this module.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", "."))
    return Path(__file__).resolve().parent


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
    raw.sort(key=lambda m: m["time"])
    merged = []
    for meal in raw:
        if merged and (meal["time"] - merged[-1]["time"]).total_seconds() <= MERGE_SEC:
            merged[-1]["cho"] += meal["cho"]
            merged[-1]["bolus"] += meal["bolus"]
            merged[-1]["bg"] = max(merged[-1]["bg"], meal["bg"])
        else:
            merged.append(dict(meal))
    meals = [m for m in merged if m["cho"] >= MEAL_MIN_CHO and m["bolus"] > 0]
    minors = [m for m in merged if m["cho"] < MEAL_MIN_CHO or m["bolus"] <= 0]
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
    segs.sort()
    t0 = segs[0][0]
    minutes = int((segs[-1][0] + timedelta(minutes=segs[-1][1]) - t0).total_seconds() // 60) + 1
    rate = np.full(minutes, np.nan)
    for start, dur, value in segs:
        i0 = int((start - t0).total_seconds() // 60)
        rate[i0:i0 + max(dur, 1)] = value
    last = segs[0][2]
    for i in range(minutes):
        if np.isnan(rate[i]):
            rate[i] = last
        else:
            last = rate[i]
    fasting_idx = [i for i in range(minutes)
                   if (t0 + timedelta(minutes=i)).hour in FASTING_HOURS]
    # Mean (not median): under Auto Mode the loop frequently suspends the basal
    # rate to 0 and runs peaks in between. The median then reflects rather HOW OFTEN
    # it is suspended, the mean the actually delivered insulin AMOUNT -- and as the
    # reference for the loop extra basal (an amount/area) the mean is the
    # consistent reference quantity.
    fasting = float(np.mean([rate[i] for i in fasting_idx]))
    # Spread across nights: mean per night, then range. For strongly varying
    # nights a single fasting basal rate is not very meaningful.
    per_night = defaultdict(list)
    for i in fasting_idx:
        per_night[(t0 + timedelta(minutes=i)).date()].append(rate[i])
    night_means = [float(np.mean(v)) for v in per_night.values() if v]
    fasting_lo = min(night_means) if night_means else fasting
    fasting_hi = max(night_means) if night_means else fasting
    return rate, t0, minutes, fasting, fasting_lo, fasting_hi




def _libreview_csv(base):
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
    return _libreview_csv(base) is not None


def read_libreview(base):
    """LibreView CSV → same dict as read_nightscout. Always lite (no basal).

    Record types: 0 historic CGM, 1 scan (fallback), 4 rapid insulin, 5 carbs.
    """
    path = _libreview_csv(base)
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
    times = np.array(times)
    gluc = np.array(gluc)
    order = np.argsort(times, kind="stable")
    times, gluc = times[order], gluc[order]
    keep = np.concatenate(([True], times[1:] != times[:-1]))
    times, gluc = times[keep], gluc[keep]
    raw.sort(key=lambda m: m["time"])
    merged = []
    for meal in raw:
        if merged and (meal["time"] - merged[-1]["time"]).total_seconds() <= MERGE_SEC:
            merged[-1]["cho"] += meal["cho"]
            merged[-1]["bolus"] += meal["bolus"]
        else:
            merged.append(dict(meal))
    meals = [m for m in merged if m["cho"] >= MEAL_MIN_CHO and m["bolus"] > 0]
    minors = [m for m in merged if m["cho"] < MEAL_MIN_CHO or m["bolus"] <= 0]
    events = [{"time": m["time"], "cho": m["cho"], "bolus": m["bolus"]} for m in merged]
    return {
        "times": times, "gluc": gluc, "name": name, "sensor": sensor,
        "meals": meals, "minors": minors, "pump": "LibreView",
        "basal": None, "events": events, "tdd": {}, "source": "libreview",
    }



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

def is_nightscout(base):
    """True if this folder (or a child) is a Nightscout entries+treatments dump."""
    return _nightscout_dir(base) is not None


def _nightscout_dir(base):
    base = Path(base)
    for cand in (base, *(p.parent for p in base.rglob("entries.json"))):
        if (cand / "entries.json").is_file() and (cand / "treatments.json").is_file():
            return cand
    return None


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
    times = np.array(times)
    gluc = np.array(gluc)
    order = np.argsort(times, kind="stable")
    times, gluc = times[order], gluc[order]
    keep = np.concatenate(([True], times[1:] != times[:-1]))
    times, gluc = times[keep], gluc[keep]
    raw = []
    for row in treatments:
        ts = _ns_parse_time(row, offset)
        if ts is None:
            continue
        cho = float(row["carbs"]) if row.get("carbs") not in (None, "") else 0.0
        ins = float(row["insulin"]) if row.get("insulin") not in (None, "") else 0.0
        if cho > 0 or ins > 0:
            raw.append({"time": ts, "cho": cho, "bg": np.nan, "bolus": ins})
    raw.sort(key=lambda m: m["time"])
    merged = []
    for meal in raw:
        if merged and (meal["time"] - merged[-1]["time"]).total_seconds() <= MERGE_SEC:
            merged[-1]["cho"] += meal["cho"]
            merged[-1]["bolus"] += meal["bolus"]
        else:
            merged.append(dict(meal))
    meals = [m for m in merged if m["cho"] >= MEAL_MIN_CHO and m["bolus"] > 0]
    minors = [m for m in merged if m["cho"] < MEAL_MIN_CHO or m["bolus"] <= 0]
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


def loop_rest(basal, meals):
    """Meal-free stretches vs fasting basal → quiet / active / unclear.

    Nights that *define* the fasting reference are excluded (would be circular).
    This is a context flag for how readable the CR table is, not a new CR.
    """
    rate, t0, minutes, fasting = basal[:4]
    if fasting <= 0 or minutes <= 0:
        return {"state": "unclear", "windows": 0, "hours": 0.0,
                "rel": None, "off": None}
    blocked = np.zeros(minutes, dtype=bool)
    for i in range(minutes):
        if (t0 + timedelta(minutes=i)).hour in FASTING_HOURS:
            blocked[i] = True
    for m in meals:
        i0 = int((m["time"] - t0).total_seconds() // 60)
        a = max(0, i0)
        b = min(minutes, i0 + REST_EXCL_AFTER_MEAL_MIN)
        if b > a:
            blocked[a:b] = True
    windows = []
    i = 0
    while i < minutes:
        if blocked[i]:
            i += 1
            continue
        j = i
        while j < minutes and not blocked[j]:
            j += 1
        if j - i >= REST_MIN_WINDOW_MIN:
            sl = rate[i:j]
            mean_r = float(np.mean(sl))
            rel = (mean_r / fasting) - 1.0
            off = float(np.mean(np.abs(sl / fasting - 1.0) >= REST_REL))
            extra_u = float(np.sum(sl - fasting) / 60.0)
            windows.append({
                "min": j - i, "rel": rel, "off": off, "extra_u": extra_u,
            })
        i = j
    hours = sum(w["min"] for w in windows) / 60.0
    n = len(windows)
    if n < REST_MIN_WINDOWS or hours < REST_MIN_HOURS:
        state = "unclear"
        rel = off = None
    else:
        rel = float(np.median([abs(w["rel"]) for w in windows]))
        off = float(np.median([w["off"] for w in windows]))
        state = "active" if (rel >= REST_REL or off >= REST_OFF_FRAC) else "quiet"
    return {"state": state, "windows": n, "hours": hours, "rel": rel, "off": off}



# --- Analysis ---------------------------------------------------------------
def consensus_metrics(times, gluc):
    """Consensus metrics (Battelino 2019) as a dict.

    Works in the active glucose unit: gluc and all thresholds are in that unit
    (g() converts the mg/dL consensus cut-offs). GMI is defined on a mg/dL mean,
    so the mean is converted back to mg/dL for that formula regardless of unit.
    """
    mean, sd = float(gluc.mean()), float(gluc.std())
    days = (times[-1] - times[0]).total_seconds() / 86400
    step = np.median(np.diff([t.timestamp() for t in times])) / 60
    mean_mgdl = mean * MGDL_PER_MMOL if is_mmol() else mean

    def pct(lo, hi):
        return 100 * float(np.mean((gluc >= lo) & (gluc <= hi)))

    return {
        "mean": mean, "cv": sd / mean * 100, "gmi": 3.31 + 0.02392 * mean_mgdl, "days": days,
        "wear": 100 * len(gluc) / (days * 24 * 60 / step) if step else float("nan"),
        "tir": pct(g(70), g(180)), "titr": pct(g(70), g(140)),
        "tbr1": 100 * float(np.mean((gluc >= g(54)) & (gluc < g(70)))),
        "tbr2": 100 * float(np.mean(gluc < g(54))),
        "tar1": 100 * float(np.mean((gluc > g(180)) & (gluc <= g(250)))),
        "tar2": 100 * float(np.mean(gluc > g(250))),
    }


def make_glucose_lookup(times, gluc):
    """Closure: mean glucose ~minutes after ref (+-tol). Same window as before.

    ``times`` is sorted. Lookup is by binary search so long CGM traces stay
    cheap; the value is still the arithmetic mean of every sample in [lo, hi].
    """
    t64 = np.asarray(times, dtype="datetime64[ns]")
    g64 = np.asarray(gluc, dtype=float)

    def val_at(ref, minutes, tol=12):
        lo = np.datetime64(ref + timedelta(minutes=minutes - tol), "ns")
        hi = np.datetime64(ref + timedelta(minutes=minutes + tol), "ns")
        i = int(np.searchsorted(t64, lo, side="left"))
        j = int(np.searchsorted(t64, hi, side="right"))
        if j <= i:
            return np.nan
        return float(np.mean(g64[i:j]))
    return val_at


def cgm_gap_in_window(start, window_min, times, max_gap_min=MAX_GAP_MIN):
    """True if CGM coverage in ``[start, start+window]`` has a gap above ``max_gap_min``.

    Gaps are measured between consecutive CGM samples inside the window and at
    the edges (meal start → first sample, last sample → window end). No sample
    in the window counts as a gap. Used to exclude poorly covered meals from the
    clean median when enough alternatives exist (see :func:`select_slot_rows`).
    """
    if times is None or len(times) == 0:
        return True
    end = start + timedelta(minutes=int(window_min))
    t64 = np.asarray(times, dtype="datetime64[ns]")
    i = int(np.searchsorted(t64, np.datetime64(start, "ns"), side="left"))
    j = int(np.searchsorted(t64, np.datetime64(end, "ns"), side="right"))
    if j <= i:
        return True
    limit = np.timedelta64(int(max_gap_min), "m")
    win = t64[i:j]
    if win[0] - np.datetime64(start, "ns") > limit:
        return True
    if np.datetime64(end, "ns") - win[-1] > limit:
        return True
    if win.size > 1 and np.any(np.diff(win) > limit):
        return True
    return False


def _scan_minors(start, window, minors, val_at):
    """Scan small carb entries in a meal's window -> (contaminated, hypo_rescue)."""
    contam = hypo = False
    for minor in minors:
        dt = (minor["time"] - start).total_seconds()
        if 0 < dt <= window * 60:
            contam = True
            g_now = val_at(minor["time"], 0)
            if minor["bolus"] <= 0 and not np.isnan(g_now) and g_now < g(HYPO_BG):
                hypo = True
    return contam, hypo


def analyze_meals(meals, minors, basal, window, val_at, cgm_times=None):
    """Per meal: loop extra basal in the window, CR_eff, return Δ, contamination, CGM gap.

    basal: (rate, t0, minutes, fasting, fasting_lo, fasting_hi) from read_basal_timeline.
    minors: small carb entries (snacks / hypo rescues) below the meal bar. A minor
    inside a meal's window contaminates it; a minor with no bolus at low glucose is
    treated as a hypo rescue, which additionally sets a hypo flag on the meal.
    cgm_times: CGM timestamps for :func:`cgm_gap_in_window` (optional; gap=False if omitted).
    """
    rate, t0, minutes, fasting = basal[:4]
    meal_times = [m["time"] for m in meals]
    rows = []
    for meal in meals:
        start = meal["time"]
        i0 = int((start - t0).total_seconds() // 60)
        if i0 < 0 or i0 + window >= minutes:
            continue
        contam = any(0 < (o - start).total_seconds() <= window * 60
                     for o in meal_times if o != start)
        minor_contam, hypo_rescue = _scan_minors(start, window, minors, val_at)
        contam = contam or minor_contam
        cgm_gap = cgm_gap_in_window(start, window, cgm_times) if cgm_times is not None else False
        excess = float(np.sum(rate[i0:i0 + window] - fasting) / 60.0)
        pre, post = val_at(start, 0), val_at(start, window)
        total = meal["bolus"] + excess
        rows.append({
            "slot": slot_of(start.hour), "time": start, "cho": meal["cho"],
            "bg": meal["bg"], "bolus": meal["bolus"], "pre": pre,
            "cr": meal["cho"] / meal["bolus"], "exc": excess,
            "cr_eff": meal["cho"] / total if total > 0 else np.nan,
            "d4": (post - pre) if not np.isnan(post) and not np.isnan(pre) else np.nan,
            "contam": contam, "hypo_rescue": hypo_rescue, "cgm_gap": cgm_gap,
        })
    return rows


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


def verdict_class(exc, bol, d4):
    """The verdict rule itself: median extra basal / bolus / Δ4h -> class.

    Single source of truth, shared by :func:`aggregate_slot` and the
    decision-stability bootstrap, so a resampled verdict can never drift
    from the real one.
    """
    ratio = exc / bol if bol else 0
    if ratio > LOOP_RATIO or d4 > g(D4_HIGH):
        return "weak"
    if ratio < -LOOP_RATIO or d4 < g(D4_STRONG):
        return "strong"
    return "ok"


def observed_range(use_rows, key="cr_eff"):
    """Plain min/max of a quantity across the meals. -> (lo, hi, n) or None.

    Fallback for slots below the bootstrap gates: a resampled 95 % spread would
    pretend to a precision the data cannot carry, but the range actually seen is
    a fact and still tells the reader how far the meals sit apart. Needs at
    least two usable values.
    """
    vals = [r[key] for r in use_rows if not np.isnan(r[key])]
    if len(vals) < 2:
        return None
    return min(vals), max(vals), len(vals)


def decision_stability(use_rows, n_boot=BOOTSTRAP_N, seed=BOOTSTRAP_SEED):
    """How often the slot's verdict survives resampling its meals. -> dict|None.

    Resamples whole **days** with replacement (not individual meals): meals of
    one day share basal need, sensor and daily routine, so treating them as
    independent draws would overstate how much evidence there is.

    Returns ``{"pct", "cls", "dist", "band", "days"}`` where ``pct`` is the
    share of resamples reproducing the class of the full sample, or ``None``
    when there is too little data (see :data:`MIN_MEALS_FOR_STABILITY` /
    :data:`MIN_DAYS_FOR_STABILITY`) — a stability figure from a handful of
    meals looks reassuring without being informative.

    This measures sensitivity to *which meals happened to be recorded*, not
    whether the carb ratio itself is right. The same pass also records the
    spread of CR_eff and of the loop share over those resampled days, reported
    as ``spread`` (2.5th/97.5th percentile) — deliberately not called a
    confidence interval: it covers the choice of days only, not the systematic
    confounding by loop adaptation.
    """
    by_day = {}
    for row in use_rows:
        by_day.setdefault(row["time"].date(), []).append(row)
    days = list(by_day.values())
    if len(use_rows) < MIN_MEALS_FOR_STABILITY or len(days) < MIN_DAYS_FOR_STABILITY:
        return None

    pos, day_index = 0, []
    for rows in days:
        day_index.append(np.arange(pos, pos + len(rows)))
        pos += len(rows)
    order = [r for rows in days for r in rows]          # array order == day order
    exc = np.array([r["exc"] for r in order], dtype=float)
    bol = np.array([r["bolus"] for r in order], dtype=float)
    d4v = np.array([r["d4"] for r in order], dtype=float)
    cre = np.array([r["cr_eff"] for r in order], dtype=float)

    rng = np.random.default_rng(seed)                   # fixed: reports stay reproducible
    counts = {"weak": 0, "ok": 0, "strong": 0}
    cre_boot, ratio_boot = [], []
    with warnings.catch_warnings():                     # all-NaN slices are expected
        warnings.simplefilter("ignore", RuntimeWarning)
        for pick in rng.integers(0, len(days), size=(n_boot, len(days))):
            idx = np.concatenate([day_index[i] for i in pick])
            m_exc = float(np.nanmedian(exc[idx]))
            m_bol = float(np.nanmedian(bol[idx]))
            counts[verdict_class(m_exc, m_bol, float(np.nanmedian(d4v[idx])))] += 1
            cre_boot.append(float(np.nanmedian(cre[idx])))
            ratio_boot.append(m_exc / m_bol if m_bol else np.nan)

        cls = verdict_class(float(np.nanmedian(exc)), float(np.nanmedian(bol)),
                            float(np.nanmedian(d4v)))
        spread = {key: tuple(np.nanpercentile(np.array(vals, dtype=float), [2.5, 97.5]))
                  for key, vals in (("cre", cre_boot), ("ratio", ratio_boot))
                  if not np.all(np.isnan(vals))}
    pct = 100.0 * counts[cls] / n_boot
    band = ("high" if pct >= STABILITY_HIGH
            else "moderate" if pct >= STABILITY_MODERATE else "low")
    return {"pct": pct, "cls": cls, "band": band, "days": len(days),
            "dist": {k: 100.0 * v / n_boot for k, v in counts.items()},
            "spread": spread}


def aggregate_slot(slot_rows):
    """Median aggregation of a slot + verdict. -> dict or None."""
    use, n_clean, used_clean_only = select_slot_rows(slot_rows)
    if not use:
        return None
    low_confidence = not used_clean_only     # verdict relies (also) on contaminated meals

    def med(key):
        vals = [r[key] for r in use if not np.isnan(r[key])]
        return float(np.nanmedian(vals)) if vals else np.nan

    exc, bol, d4 = med("exc"), med("bolus"), med("d4")
    rescues = sum(1 for r in slot_rows if r.get("hypo_rescue"))
    cls = verdict_class(exc, bol, d4)
    flag = {"weak": _("too weak → tighten"),
            "strong": _("too strong → loosen"),
            "ok": _("plausibly adequate")}[cls]
    # A hypo rescue means an individual meal went low enough to need treatment.
    # How that reflects on the slot depends on the verdict and on how many meals
    # are affected — a single rescue among many meals is scatter, not a systematic
    # "too strong". "n" here is the number of meals in the slot.
    if rescues:
        n = len(slot_rows)
        systematic = rescues >= max(2, n / 4)   # a relevant share (>=25%), not a one-off
        if cls == "strong":
            flag += _(" ⚠︎ (hypo treated)")
        elif cls == "ok" and systematic:
            # the balanced median is propped up by the rescue carbs
            flag += _(" ⚠︎ (hypo rescue — likely too strong)")
        else:
            # weak, or ok with only isolated rescues: a mixed picture, not "too strong"
            flag += _(" ⚠︎ (isolated hypo(s) — mixed, check meals individually)")
    else:
        systematic = False
    # Deliberately also spelled out in the verdict text, not only as a badge:
    # the wording survives copy/paste and print, where the badge is easy to miss.
    if low_confidence:
        flag += _(" ⚠︎ (few clean meals)")
    return {"n": len(slot_rows), "clean": n_clean, "cho": med("cho"), "cr": med("cr"),
            "bol": bol, "exc": exc, "cre": med("cr_eff"), "d4": d4, "flag": flag, "cls": cls,
            "rescues": rescues, "systematic": systematic, "low_confidence": low_confidence}


def slot_median_curve(meals, slot, window, val_at):
    """Median postprandial curve (0..window) of a slot or None."""
    grid = np.arange(0, window + 1, 10)
    stacks = [[val_at(m["time"], int(g), 6) for g in grid]
              for m in meals if slot_of(m["time"].hour) == slot]
    return np.nanmedian(np.array(stacks), axis=0) if stacks else None


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


def shape_description(curve):
    """Short, data-driven shape description of a postprandial curve."""
    if curve is None or np.all(np.isnan(curve)):
        return None
    start, end, low = np.nanmedian(curve[:2]), np.nanmedian(curve[-2:]), np.nanmin(curve)
    if low < 75:
        return _("rises and then falls to low values")
    if end - start > g(25):
        return _("climbs and does not return to baseline")
    if end - start < -g(25):
        return _("falls clearly below baseline")
    return _("returns close to baseline (balanced)")


def curve_metrics(curve, grid):
    """Peak/nadir/start/end + 'still rising at the end' from a postprandial curve."""
    pk, nd = int(np.nanargmax(curve)), int(np.nanargmin(curve))
    return {"start": float(np.nanmedian(curve[:2])), "end": float(np.nanmedian(curve[-2:])),
            "peak": float(curve[pk]), "peak_t": int(grid[pk]),
            "nadir": float(curve[nd]), "nadir_t": int(grid[nd]),
            "rising_end": float(curve[-1]) - float(curve[-3]) > 5}


def _weak_levers(agg, window):
    """Levers for a 'weak' slot (underdosed / loop pushes extra)."""
    ratio = agg["exc"] / agg["bol"] if agg["bol"] else 0
    if ratio <= LOOP_RATIO:
        return [(_("Caution"), "obs",
                 _("BG clearly elevated at the end of the window, but the loop rather throttled "
                   "(contradictory signal) → possibly an outlier/small sample size "
                   "rather than a CR problem; check individual meals before tightening"))]
    out = [(_("Dose"), "cr",
            _("underdosed → tighten CR, rough direction CR_eff %(cre)s") % {"cre": fmt_cr(agg["cre"])})]
    if agg["d4"] < 0:
        # The verdict comes solely from the loop activity; but the BG has even
        # fallen at the end of the window (the loop caught it). To the reader,
        # "tighten" next to a negative Δ4h looks like an error -- name the contradiction.
        out.append((_("Caution"), "obs",
                    _("Δ%(h)dh is negative (BG fell at the end); the verdict here rests solely on "
                      "the strong loop extra basal — the loop caught the too-weak CR. Before "
                      "tightening, check individual meals and contamination") % {"h": window // 60}))
    return out


def _hypo_caution(agg, met, curve_hypo):
    """Caution lever for a hypo in the window, worded to match the slot verdict so
    it never contradicts the dose direction. Fires either on a deep median-curve
    nadir (curve_hypo) or on a documented rescue. When only a rescue is present
    (the median curve itself doesn't dip low), the text refers to the treated
    low rather than the median nadir value, which would understate it.
      - no rescue (curve hypo only) -> preventive "secure the hypo window first"
      - rescue + too strong / systematic -> a treated hypo, reduce the dose here
      - rescue + otherwise (weak / isolated-in-ok) -> a treated hypo on one meal,
        check that meal rather than tightening the whole slot.
    """
    base = {"n": met["nadir"], "t": met["nadir_t"], "u": glucose_unit()}
    if not agg.get("rescues"):
        return (_("Caution"), "obs", _("nadir ~%(n).0f %(u)s around %(t)d min "
                                       "→ secure the hypo window first") % base)
    reduce_dose = agg["cls"] == "strong" or agg.get("systematic")
    if curve_hypo:
        if reduce_dose:
            return (_("Caution"), "obs", _("nadir ~%(n).0f %(u)s around %(t)d min — a hypo "
                                           "occurred and was treated; reduce the dose here") % base)
        return (_("Caution"), "obs", _("nadir ~%(n).0f %(u)s around %(t)d min — a hypo occurred "
                                       "and was treated on one meal; check that meal, do not tighten "
                                       "the whole slot") % base)
    # rescue only, median curve stays out of the hypo range
    if reduce_dose:
        return (_("Caution"), "obs", _("a hypo occurred and was treated in the window; "
                                       "reduce the dose here"))
    return (_("Caution"), "obs", _("a hypo occurred and was treated on one meal; check that "
                                   "meal, do not tighten the whole slot"))


def slot_levers(agg, met, window):
    """Candidate levers (tag, CSS class, text) from verdict + curve shape."""
    levers = []
    if met["peak_t"] <= PEAK_EARLY and met["peak"] - met["start"] >= g(PEAK_RISE_HIGH):
        levers.append((_("Pre-bolus"), "sea", _("early high peak → try a longer bolus-meal interval "
                                                  "(caps the spike without more dose)")))
    if agg["cls"] == "weak":
        levers.extend(_weak_levers(agg, window))
    elif agg["cls"] == "strong":
        levers.append((_("Dose"), "cr", _("overdosed/drop → rather reduce the dose of this meal; "
                                           "consider pre-bolus and dose together")))
    late_rise = met["peak_t"] >= window * 0.66 and met["end"] - met["start"] > 20
    if late_rise and agg["cls"] != "ok":
        levers.append((_("Fat/protein"), "fp", _("monotonic late rise (no turning point) → check fat/protein; "
                                                   "possibly delayed/dual bolus instead of only tightening")))
    elif late_rise:
        levers.append((_("Observe"), "obs", _("slight late re-rise → possibly fat/protein or "
                                                "basal rate in this window; just keep an eye on it")))
    curve_hypo = met["nadir"] < g(NADIR_LOW) and met["nadir_t"] >= NADIR_LATE
    if curve_hypo or agg.get("rescues"):
        levers.append(_hypo_caution(agg, met, curve_hypo))
    has_hypo = met["nadir"] < g(NADIR_LOW) and met["nadir_t"] >= NADIR_LATE
    if (agg["cls"] == "ok" and not any(c == "cr" for _, c, _ in levers)
            and not has_hypo and not agg.get("systematic")):
        levers.append(_reference_lever(agg, levers))
    if not levers:
        levers.append(("—", "obs", _("no notable shape")))
    return levers


def _reference_lever(agg, levers):
    """Reference lever for an otherwise adequate slot, in three tiers by how many
    meals needed a hypo rescue (same >=25% "systematic" bar as the verdict):
    none -> "leave as is"; isolated -> point at the one low meal; systematic is
    already excluded by the caller (the verdict says "too strong")."""
    if agg.get("rescues"):
        return (_("Reference"), "obs", _("CR on average fits, but a meal went low "
                                         "(hypo rescue) — check that one, do not tighten"))
    if any(c == "sea" for _, c, _ in levers):
        return (_("Reference"), "obs", _("dose fits — leave as is; for timing see the "
                                         "pre-bolus note above"))
    return (_("Reference"), "obs", _("dose & timing fit — leave as is; "
                                     "serves as a comparison for the other slots"))


def slot_headline(agg, met):
    """Verdict-aware short description of the slot shape (consistent with verdict AND curve)."""
    rise_end = met["end"] - met["start"]
    early_high = met["peak_t"] <= PEAK_EARLY and met["peak"] - met["start"] >= g(PEAK_RISE_HIGH)
    if agg["cls"] == "strong":
        if rise_end < -g(25):                        # curve at 4h really below start
            return (_("high peak, then drop below baseline") if met["nadir"] < g(NADIR_LOW)
                    else _("falls below baseline"))
        # Verdict "strong" came from the loop signal, not from an actual curve drop
        return _("returns close to baseline, loop throttles noticeably")
    if agg["cls"] == "weak":
        return _("climbs and does not return to baseline")
    if rise_end > 20:
        return _("slight late rise, but net balanced")
    if early_high:
        return _("early peak, then returns cleanly")
    return _("returns close to baseline (balanced)")


def build_cr_note(rows, by_slot):
    """Data-driven hint about notable derived CR values (HTML snippet)."""
    all_cr = [r["cr"] for r in rows if not np.isnan(r["cr"])]
    med_cr = float(np.median(all_cr)) if all_cr else float("nan")
    dev = []
    for slot in _slot_state()[1]:
        srows = by_slot.get(slot, [])
        if len(srows) < 3:
            continue
        scr = float(np.nanmedian([r["cr"] for r in srows]))
        pres = [r["pre"] for r in srows if not np.isnan(r["pre"])]
        spre = float(np.nanmedian(pres)) if pres else float("nan")
        if not np.isnan(scr) and (scr < CR_DEV_LOW * med_cr or scr > CR_DEV_HIGH * med_cr):
            dev.append((slot, scr, spre))
    if not dev:
        return _("• Derived CR = CHO/bolus; no slot deviates notably from the median "
                 "(1:%(m).1f).<br>") % {"m": med_cr}
    parts = []
    for slot, scr, spre in dev:
        direction = _("tighter") if scr < med_cr else _("looser")
        if not np.isnan(spre) and spre > g(PRE_BG_HIGH):
            hint = _("elevated pre-meal BG → correction likely blended in by the calculator, "
                     "derived CR underestimates the programmed ratio")
        else:
            hint = _("pre-meal BG not clearly elevated → rather a genuinely different programmed "
                     "ratio than a pure correction")
        parts.append(_("%(slot)s: derived CR 1:%(scr).1f (%(dir)s than median 1:%(m).1f), "
                       "pre-meal BG ~%(bg).0f %(u)s – %(hint)s")
                     % {"slot": _slot_state()[2][slot], "scr": scr, "dir": direction,
                        "m": med_cr, "bg": spre, "hint": hint, "u": glucose_unit()})
    return (_("• Derived CR = CHO/bolus (may include blended-in corrections). Notable "
              "deviations: ") + "; ".join(parts) + _(". Clarification (programmed ratio vs. "
              "correction factor vs. timing) by the care team.<br>"))


# --- Charts -----------------------------------------------------------------
def agp_chart(times, gluc, dark=False):
    """AGP percentile chart as base64 PNG (light or dark theme)."""
    minute = np.array([t.hour * 60 + t.minute for t in times])
    bins = np.arange(0, 1441, 15)
    idx = np.digitize(minute, bins) - 1
    xs, perc = [], {q: [] for q in (5, 25, 50, 75, 95)}
    for b in range(len(bins) - 1):
        vals = gluc[idx == b]
        if len(vals) >= 5:
            xs.append((bins[b] + 7.5) / 60)
            for q in perc:
                perc[q].append(np.percentile(vals, q))
    xs = np.array(xs)
    pal = _chart_palette(dark)
    with _chart_theme(dark):
        fig, ax = plt.subplots(figsize=(10, 3.6))
        ax.axhspan(g(70), g(180), color=pal["tir"])
        ax.axhline(g(70), color="#5a5", lw=.7)
        ax.axhline(g(180), color="#5a5", lw=.7)
        ax.fill_between(xs, perc[5], perc[95], color=pal["p5"], alpha=.6, label="5–95 %")
        ax.fill_between(xs, perc[25], perc[75], color=pal["p25"], alpha=.55, label="25–75 %")
        ax.plot(xs, perc[50], color=pal["median"], lw=2, label="Median")
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 3))
        ax.set_ylim(g(40), g(300))
        ax.set_xlabel("Uhrzeit")
        ax.set_ylabel(glucose_unit())
        ax.legend(fontsize=8, ncol=3, loc="upper right")
        ax.grid(alpha=.25)
        return fig_to_b64(fig)



def slot_curves_chart(meals, window, val_at, dark=False):
    """Median postprandial curves per slot as base64 PNG (light or dark theme)."""
    grid = np.arange(0, window + 1, 10)
    pal = _chart_palette(dark)
    with _chart_theme(dark):
        fig, ax = plt.subplots(figsize=(10, 3.6))
        ax.axhspan(g(70), g(180), color=pal["tir"])
        for slot in _slot_state()[1]:
            curve = slot_median_curve(meals, slot, window, val_at)
            if curve is not None:
                n = sum(1 for meal in meals if slot_of(meal["time"].hour) == slot)
                ax.plot(grid, curve, color=_slot_state()[3][slot], lw=2,
                        label=f"{_slot_state()[2][slot]} (n={n})")
        ax.set_xlim(0, window)
        ax.set_ylim(g(60), g(240))
        ax.set_xlabel(_("Minutes after meal"))
        ax.set_ylabel(glucose_unit())
        if ax.get_legend_handles_labels()[1]:
            ax.legend(fontsize=8)
        ax.grid(alpha=.25)
        return fig_to_b64(fig)



def selection_effect(meals, by_slot, window, val_at):
    """How much the verdict's meal selection would move the normalised curves.

    The chart shows all meals; the verdict uses only uncontaminated ones. This
    quantifies the gap instead of asking the reader to compare two pictures:
    per slot, how many meals are clean and the largest deviation between the
    all-meals curve and the clean-only curve. A small number means the neutral
    chart also describes what the verdict rests on. -> list of dicts.
    """
    out = []
    for slot in _slot_state()[1]:
        rows = by_slot.get(slot, [])
        if not rows:
            continue
        use, _n_clean, clean_only = select_slot_rows(rows)
        clean_times = {r["time"] for r in use} if clean_only else None
        curve_all, n_all = slot_norm_curve(meals, slot, window, val_at, None)
        curve_sel, n_sel = slot_norm_curve(meals, slot, window, val_at, clean_times)
        if curve_all is None or curve_sel is None:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            shift = float(np.nanmax(np.abs(np.array(curve_all) - np.array(curve_sel))))
        out.append({"label": _slot_state()[2][slot], "used": n_sel, "total": n_all,
                    "shift": "—" if np.isnan(shift) else fmt_delta(shift).lstrip("+")})
    return out


def slot_norm_curves_chart(meals, window, val_at, dark=False):
    """One figure: legend + one framed card per meal (title + plot inside).

    Layout matches the design mock: nothing outside its box, no label clipping.
    """
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch, FancyBboxPatch

    bands = []
    for slot in _slot_state()[1]:
        b = slot_norm_bands(meals, slot, window, val_at, None)
        if b is not None:
            bands.append((slot, b))
    if not bands:
        with _chart_theme(dark):
            fig, ax = plt.subplots(figsize=(10, 2))
            ax.text(0.5, 0.5, "—", ha="center", va="center")
            ax.axis("off")
            return fig_to_b64(fig)

    n = len(bands)
    ncols = 2
    nrows = (n + ncols - 1) // ncols
    # Fixed Δ range; curves may clip outside −100…+150
    y_lo, y_hi = -g(100), g(150)

    pal = _chart_palette(dark)
    band90 = "#bcd4ff" if not dark else "#2a4060"
    band75 = "#5b8def" if not dark else "#3a6aaa"
    med_c = pal["median"]
    zero_c = "#888" if not dark else "#8a97a8"
    title_c = "#1a2233" if not dark else "#e8ecf2"
    edge = "#c5cdd9" if not dark else "#4a5568"
    face = "#ffffff" if not dark else "#1c2330"
    box_bg = face  # same white as plot; no grey fill around the chart
    fig_bg = face

    with _chart_theme(dark):
        # Extra top row for the legend strip
        fig = plt.figure(figsize=(10.2, 0.12 + 2.85 * nrows))
        fig.patch.set_facecolor(fig_bg)
        # gridspec: row 0 = legend, then meal rows
        height_ratios = [0.09] + [2.5] * nrows
        gs = fig.add_gridspec(
            1 + nrows, ncols,
            height_ratios=height_ratios,
            hspace=0.16, wspace=0.04,
            left=0.03, right=0.97, top=0.995, bottom=0.03,
        )

        # Legend centered across both columns
        leg_ax = fig.add_subplot(gs[0, :])
        leg_ax.set_axis_off()
        leg_ax.set_xlim(0, 1)
        leg_ax.set_ylim(0, 1)
        handles = [
            Line2D([0], [0], color=med_c, lw=2.2, label=_("Median")),
            Patch(facecolor=band75, edgecolor="none", alpha=0.85, label=_("25–75 %")),
            Patch(facecolor=band90, edgecolor="none", alpha=0.75, label=_("10–90 %")),
        ]
        leg = leg_ax.legend(
            handles=handles, loc="center", ncol=3, frameon=False,
            fontsize=7.5, handlelength=1.6, columnspacing=1.0,
            borderaxespad=0.0, handletextpad=0.35, borderpad=0.0,
        )
        for text in leg.get_texts():
            text.set_color(title_c)

        for i, (slot, b) in enumerate(bands):
            r, c = divmod(i, ncols)
            outer = fig.add_subplot(gs[1 + r, c])
            outer.set_xticks([])
            outer.set_yticks([])
            outer.set_xlim(0, 1)
            outer.set_ylim(0, 1)
            outer.set_facecolor(box_bg)
            for spine in outer.spines.values():
                spine.set_visible(True)
                spine.set_color(edge)
                spine.set_linewidth(1.5)

            outer.text(
                0.5, 0.97,
                f"{_slot_state()[2][slot]}",
                transform=outer.transAxes, ha="center", va="top",
                fontsize=11, color=title_c, fontweight="bold",
            )
            outer.text(
                0.5, 0.90,
                f"n = {b['n']}",
                transform=outer.transAxes, ha="center", va="top",
                fontsize=9, color="#5a6577" if not dark else "#a0aab8",
            )
            # Leave clear margins so axis labels never touch the outer frame
            ax = outer.inset_axes([0.15, 0.16, 0.76, 0.64])
            grid = b["grid"]
            ax.set_facecolor(face)
            ax.fill_between(grid, b["p10"], b["p90"], color=band90, alpha=.55, lw=0)
            ax.fill_between(grid, b["p25"], b["p75"], color=band75, alpha=.45, lw=0)
            ax.plot(grid, b["p50"], color=med_c, lw=2)
            ax.axhline(0, color=zero_c, lw=.8, ls="--")
            ax.set_xlim(0, window)
            ax.set_ylim(y_lo, y_hi)
            ax.set_xlabel(_("Minutes after meal"), fontsize=7, labelpad=2)
            ax.set_ylabel(
                _("Δ %(u)s vs. meal start") % {"u": glucose_unit()},
                fontsize=7, labelpad=2,
            )
            ax.tick_params(labelsize=6.5, pad=1)
            ax.grid(alpha=.2)
            for spine in ax.spines.values():
                spine.set_color("#d8dee8" if not dark else "#3a4556")

        for j in range(len(bands), nrows * ncols):
            r, c = divmod(j, ncols)
            blank = fig.add_subplot(gs[1 + r, c])
            blank.axis("off")
            blank.set_facecolor(fig_bg)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor(),
                    edgecolor="none", bbox_inches="tight", pad_inches=0.06)
        plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode()


# --- Context / Rendering ----------------------------------------------------
WEEKDAYS = (N_("Monday"), N_("Tuesday"), N_("Wednesday"), N_("Thursday"),
            N_("Friday"), N_("Saturday"), N_("Sunday"))
DAILY_BOLUS_Y, DAILY_CARB_Y, DAILY_ROW, DAILY_MIN_GAP = 452, 388, 18, 0.9


def _draw_labels(axg, items, base_y, color, bold=False):
    """Place labels (hour, text) of one kind; stagger into rows only on real proximity."""
    lanes = []
    for hour, text in sorted(items):
        lane = next((i for i, last in enumerate(lanes) if hour - last >= DAILY_MIN_GAP), None)
        if lane is None:
            lane = len(lanes)
            lanes.append(hour)
        else:
            lanes[lane] = hour
        axg.axvline(hour, color=color, lw=.4, alpha=.18)
        axg.text(hour, base_y - lane * DAILY_ROW, text, fontsize=5.5,
                 color=color, ha="center", va="top", fontweight="bold" if bold else "normal")


def _draw_day_events(axg, events, pal):
    """All bolus entries (top) and carb entries (below) of a day."""
    def hour(event):
        return event["time"].hour + event["time"].minute / 60
    _draw_labels(axg, [(hour(e), f"{e['bolus']:.1f} U") for e in events if e["bolus"] > 0],
                 DAILY_BOLUS_Y, pal["bolus"], bold=True)
    _draw_labels(axg, [(hour(e), f"{e['cho']:.0f} g") for e in events if e["cho"] > 0],
                 DAILY_CARB_Y, pal["carb"])


def _day_title(day, tdd):
    """Panel title: weekday + date, plus TDD (bolus/basal) if available."""
    title = f"{_(WEEKDAYS[day.weekday()])}, {day:%d.%m.%Y}"
    if day in tdd:
        bolus, total, basal_u = tdd[day]
        title += f"   ·   TDD {total:.1f} U (Bolus {bolus:.1f} / Basal {basal_u:.1f})"
    return title


def daily_charts(times, gluc, events, basal, tdd, dark=False):
    """One page-wide panel per day (CGM + bolus/carb + optional basal + TDD)."""
    if basal is None:
        rate, t0, minutes, gmax = None, None, 0, 1.0
    else:
        rate, t0, minutes = basal[:3]
        gmax = float(np.nanmax(rate)) or 1.0
    cgm_by, ev_by = defaultdict(list), defaultdict(list)
    for time, value in zip(times, gluc):
        cgm_by[time.date()].append((time.hour + time.minute / 60, value))
    for event in events:
        ev_by[event["time"].date()].append(event)
    pal = _chart_palette(dark)
    out = []
    with _chart_theme(dark):
        for day in sorted(cgm_by):
            fig, axg = plt.subplots(figsize=(11, 2.5))
            axg.axhspan(g(70), g(180), color=pal["tir"])
            axg.plot([x for x, _ in cgm_by[day]], [y for _, y in cgm_by[day]],
                     color=pal["cgm"], lw=1.0)
            axg.set_xlim(0, 24)
            axg.set_ylim(g(40), g(470))
            axg.set_xticks(range(0, 25, 3))
            axg.set_yticks([g(70), g(180), g(300)])
            axg.tick_params(labelsize=7)
            axg.grid(axis="x", alpha=.15)
            title_color = "#e8ecf2" if dark else "#1a2233"
            axg.set_title(_day_title(day, tdd), fontsize=8, loc="left", color=title_color)
            if rate is not None:
                i0 = int((datetime(day.year, day.month, day.day) - t0).total_seconds() // 60)
                bxx = [mnt / 60 for mnt in range(0, 24 * 60, 5)]
                byy = [rate[i0 + mnt] if 0 <= i0 + mnt < minutes else 0.0
                       for mnt in range(0, 24 * 60, 5)]
                ax2 = axg.twinx()
                ax2.fill_between(bxx, byy, step="pre", color=pal["basal"], alpha=.35, lw=0)
                ax2.set_ylim(0, gmax * 2.2)
                ax2.set_xlim(0, 24)
                ax2.set_yticks([0, round(gmax, 1)])
                spine = "#8bb4ff" if dark else "#3a63a8"
                ax2.set_ylabel("U/h", fontsize=6, color=spine)
                ax2.tick_params(labelsize=6, colors=spine)
            _draw_day_events(axg, ev_by.get(day, []), pal)
            out.append({"img": fig_to_b64(fig)})
    return out



def slot_definitions():
    """Human-readable slot time windows for the report legend, derived from _slot_state()[0]."""
    labels = _slot_state()[2]
    out = []
    for key, _lab, start, end in _slot_state()[0]:
        label = labels.get(key, _lab)
        if start < 0:
            out.append(_("%(label)s = everything outside the other windows") % {"label": label})
        else:
            out.append(_("%(label)s = %(start)s–%(end)s") % {
                "label": label, "start": f"{start:02d}:00", "end": f"{end:02d}:00"})
    return out


def _slot_flag(agg, slot, meals, window, val_at):
    """Verdict flag for a slot, adding a hypo note when a low was reached but not
    already flagged as a rescue (rescue is the stronger, evidence-based signal)."""
    flag = agg["flag"]
    if agg["cls"] == "ok" and not agg.get("rescues"):
        curve = slot_median_curve(meals, slot, window, val_at)
        if curve is not None:
            met = curve_metrics(curve, np.arange(0, window + 1, 10))
            if met["nadir"] < g(NADIR_LOW) and met["nadir_t"] >= NADIR_LATE:
                flag += _(" ⚠︎ (hypo — secure first)")
    return flag


def _fmt_stability(stab):
    """Stability dict -> template-ready strings (or None)."""
    if stab is None:
        return None
    return {"pct": f"{stab['pct']:.0f}", "band": stab["band"], "days": stab["days"],
            "few_days": stab["days"] < FEW_DAYS_HINT}


def _fmt_spread(stab):
    """Day-to-day spread of CR_eff and loop share -> display strings (or None).

    Only the two quantities a reader acts on: CR_eff (the number that invites
    being read as a target) and the loop share (the number the threshold is
    applied to). Nominal CR is a setting rather than an estimate, and the Δ4h
    spread is regularly wider than the value itself — neither adds information.
    """
    if stab is None or not stab.get("spread"):
        return None
    out = {}
    cre = stab["spread"].get("cre")
    if cre and not any(np.isnan(v) for v in cre):
        out["cre"] = f"{fmt_cr(cre[0])} – {fmt_cr(cre[1])}"
    ratio = stab["spread"].get("ratio")
    if ratio and not any(np.isnan(v) for v in ratio):
        out["ratio"] = f"{ratio[0] * 100:+.0f} … {ratio[1] * 100:+.0f} %"
    return out or None


def _fmt_range(use_rows):
    """Observed CR_eff range -> display strings (or None), for gated slots."""
    rng = observed_range(use_rows, "cr_eff")
    if rng is None:
        return None
    lo, hi, n = rng
    days = len({r["time"].date() for r in use_rows})
    return {"cre": f"{fmt_cr(lo)} – {fmt_cr(hi)}", "meals": n, "days": days}


def _slots_context(by_slot, meals, window, val_at, stability=None, selected=None):
    out = []
    stability = stability or {}
    selected = selected or {}
    for slot, _label, _start, _end in _slot_state()[0]:
        agg = aggregate_slot(by_slot.get(slot, []))
        if not agg:
            continue
        stab = stability.get(slot)
        out.append({
            "label": _slot_state()[2][slot], "n": agg["n"], "clean": agg["clean"],
            "cho": f"{agg['cho']:.0f}", "cr": fmt_cr(agg["cr"]), "bol": f"{agg['bol']:.1f}",
            "exc": f"{agg['exc']:+.2f}", "cre": fmt_cr(agg["cre"]), "d4": fmt_delta(agg["d4"]),
            "flag": _slot_flag(agg, slot, meals, window, val_at), "cls": agg["cls"],
            "low_confidence": agg.get("low_confidence", False),
            "stability": _fmt_stability(stab),
            "spread": _fmt_spread(stab),
            "range": (None if stab else _fmt_range(selected.get(slot, []))),
        })
    return out


def _meals_context(rows):
    out = []
    for row in sorted(rows, key=lambda r: r["time"]):
        # No verdict class per meal: the row colours used to mirror the slot table
        # while following a different rule, and a single meal carries almost no
        # signal (see VALIDATION.md). Only a marked drop is flagged, on the Δ4h
        # value itself — that is a measurement, not an assessment.
        low_d4 = not np.isnan(row["d4"]) and row["d4"] < g(D4_STRONG)
        out.append({
            "time": f"{row['time']:%d.%m %H:%M}", "label": _slot_state()[2][row["slot"]],
            "cho": f"{row['cho']:.0f}", "bolus": f"{row['bolus']:.1f}", "cr": fmt_cr(row["cr"]),
            "exc": "—" if np.isnan(row["exc"]) else f"{row['exc']:+.2f}", "cre": fmt_cr(row["cr_eff"]),
            "d4": fmt_delta(row["d4"]) if not np.isnan(row["d4"]) else "—",
            "contam": row["contam"], "hypo_rescue": row.get("hypo_rescue", False),
            "cgm_gap": row.get("cgm_gap", False),
            "low_d4": low_d4,
        })
    return out


def _captions(meals, by_slot, window, val_at):
    """(curve_cap, clean_note) data-driven from the slot curves/contaminations."""
    caps = []
    for slot in _slot_state()[1]:
        desc = shape_description(slot_median_curve(meals, slot, window, val_at))
        if desc:
            caps.append(f"{_slot_state()[2][slot]} {desc}")
    curve_cap = "; ".join(caps) + "." if caps else \
        _("Too few meals per slot for a robust shape description.")
    low_clean = [_slot_state()[2][s] for s in _slot_state()[1] if by_slot.get(s)
                 and sum(not r["contam"] for r in by_slot[s]) / len(by_slot[s]) < 0.5]
    clean_note = f" (v.a. {', '.join(low_clean)})" if low_clean else ""
    return curve_cap, clean_note


def _recommendations_context(meals, by_slot, window, val_at, stability=None, selected=None):
    """Per slot: curve metrics + derived levers; plus CR_eff example."""
    grid = np.arange(0, window + 1, 10)
    recs, example, example_exc = [], None, 0.0
    stability = stability or {}
    selected = selected or {}
    for slot in _slot_state()[1]:
        curve = slot_median_curve(meals, slot, window, val_at)
        agg = aggregate_slot(by_slot.get(slot, []))
        if curve is None or agg is None or np.all(np.isnan(curve)):
            continue
        met = curve_metrics(curve, grid)
        recs.append({
            "label": _slot_state()[2][slot], "cls": agg["cls"], "headline": slot_headline(agg, met),
            "peak": fmt_glucose(met["peak"]), "peak_t": met["peak_t"],
            "nadir": fmt_glucose(met["nadir"]), "nadir_t": met["nadir_t"],
            "d4": fmt_delta(agg["d4"]), "loop": f"{agg['exc']:+.2f}",
            "cr": fmt_cr(agg["cr"]), "cre": fmt_cr(agg["cre"]),
            "low_confidence": agg.get("low_confidence", False),
            "stability": _fmt_stability(stability.get(slot)),
            "spread": _fmt_spread(stability.get(slot)),
            "range": (None if stability.get(slot)
                      else _fmt_range(selected.get(slot, []))),
            "levers": [{"tag": t, "cls": c, "text": x} for t, c, x in slot_levers(agg, met, window)],
        })
        if agg["cls"] == "weak" and (example is None or agg["exc"] > example_exc):
            example, example_exc = ({"label": _slot_state()[2][slot], "cho": f"{agg['cho']:.0f}",
                                     "bol": f"{agg['bol']:.1f}", "loop": f"{agg['exc']:.1f}",
                                     "cre": fmt_cr(agg["cre"]), "d4": fmt_delta(agg["d4"]),
                                     "underdosed": agg["d4"] > g(D4_WEAK)}, agg["exc"])
    return recs, example


def _tir_bands(met):
    """Time-in-ranges band labels (unit-aware) with values and colours."""
    return [(_("Very High &gt;%(v)s") % {"v": fmt_glucose(g(250))}, met["tar2"], "#b23b3b"),
            (_("High %(lo)s–%(hi)s") % {"lo": fmt_glucose(g(181)), "hi": fmt_glucose(g(250))},
             met["tar1"], "#e0913a"),
            (_("Target %(lo)s–%(hi)s") % {"lo": fmt_glucose(g(70)), "hi": fmt_glucose(g(180))},
             met["tir"], "#3a9b46"),
            (_("Low %(lo)s–%(hi)s") % {"lo": fmt_glucose(g(54)), "hi": fmt_glucose(g(69))},
             met["tbr1"], "#c0392b"),
            (_("Very Low &lt;%(v)s") % {"v": fmt_glucose(g(54))}, met["tbr2"], "#7d1f1f")]



def _daily_days_dual(times, gluc, base, basal, dark_charts=False, events=None, tdd=None):
    """Daily panels for the HTML report. Dark copies only if requested."""
    events = read_bolus_events(base) if events is None else events
    tdd = read_tdd(base) if tdd is None else tdd
    light = daily_charts(times, gluc, events, basal, tdd, dark=False)
    if not dark_charts:
        return [{"img": a["img"], "img_dark": ""} for a in light]
    dark = daily_charts(times, gluc, events, basal, tdd, dark=True)
    return [{"img": a["img"], "img_dark": b["img"]} for a, b in zip(light, dark)]


def build_context(base, window, wlab, daily=False, lang="de", dark_charts=False,
                  assume_camaps=False, date_from=None, date_to=None):
    """Read all data, analyse, and assemble the template context."""
    ns = None
    if is_nightscout(base):
        ns = read_nightscout(base)
    elif is_libreview(base):
        ns = read_libreview(base)
    if ns:
        times, gluc, name, sensor = ns["times"], ns["gluc"], ns["name"], ns["sensor"]
        meals, minors, pump = ns["meals"], ns["minors"], ns["pump"]
        basal = ns["basal"]
    else:
        times, gluc, name, sensor = read_cgm(base)
        meals, minors, pump = read_meals(base)
        basal = read_basal_timeline(base)
    source = ns["source"] if ns else "glooko"
    lite = source == "libreview" or (source == "nightscout" and not assume_camaps)
    events = ns["events"] if ns else None
    times, gluc, meals, minors, events = clip_by_days(
        times, gluc, meals, minors, events, date_from, date_to, window)
    val_at = make_glucose_lookup(times, gluc)

    met = consensus_metrics(times, gluc)
    if basal is None and not lite:
        raise LoopCRError("No basal rates found.")
    rows = [] if basal is None else analyze_meals(
        meals, minors, basal, window, val_at, cgm_times=times)
    seen = {r["time"] for r in rows}
    for meal in meals:
        if meal["time"] in seen:
            continue
        pre, post = val_at(meal["time"], 0), val_at(meal["time"], window)
        rows.append({
            "slot": slot_of(meal["time"].hour), "time": meal["time"],
            "cho": meal["cho"], "bg": meal.get("bg"), "bolus": meal["bolus"],
            "pre": pre, "cr": meal["cho"] / meal["bolus"] if meal["bolus"] else float("nan"),
            "exc": float("nan"), "cr_eff": float("nan"),
            "d4": (post - pre) if not np.isnan(post) and not np.isnan(pre) else np.nan,
            "contam": False, "hypo_rescue": False,
            "cgm_gap": cgm_gap_in_window(meal["time"], window, times) if times is not None else False,
        })
    by_slot = defaultdict(list)
    for row in rows:
        by_slot[row["slot"]].append(row)
    curve_cap, clean_note = _captions(meals, by_slot, window, val_at)
    if lite:
        selected, stability, recs, cr_example = {}, {}, [], None
    else:
        selected = {slot: select_slot_rows(srows)[0] for slot, srows in by_slot.items()}
        stability = {slot: decision_stability(srows) for slot, srows in selected.items()}
        recs, cr_example = _recommendations_context(meals, by_slot, window, val_at,
                                                    stability, selected)
    device = " · ".join(p for p in (pump, sensor) if p) or _("device unknown")

    return {
        "source": source, "lite": lite,
        "tool": TOOL_NAME, "name": name, "span": f"{times[0]:%d.%m.%Y}–{times[-1]:%d.%m.%Y}",
        "generated": datetime.now().strftime("%d.%m.%Y, %H:%M"), "repo": REPO_URL,
        "version": tool_version(), "lang": lang,
        "days": f"{met['days']:.0f}", "device": device if lite else f"{device} · Auto Mode",
        "wear": f"{met['wear']:.0f}", "mean": fmt_glucose(met["mean"]), "gmi": f"{met['gmi']:.1f}",
        "cv": f"{met['cv']:.0f}", "tir": f"{met['tir']:.0f}", "titr": f"{met['titr']:.0f}",
        "tir_bands": [{"label": lab, "val": f"{val:.1f}", "width": f"{min(val, 100):.1f}",
                       "color": col} for lab, val, col in _tir_bands(met)],
        "agp_img": agp_chart(times, gluc), "agp_img_dark": agp_chart(times, gluc, dark=True),
        "slot_img": slot_curves_chart(meals, window, val_at),
        "slot_img_dark": slot_curves_chart(meals, window, val_at, dark=True),
        "slot_norm_img": slot_norm_curves_chart(meals, window, val_at),
        "slot_norm_img_dark": slot_norm_curves_chart(meals, window, val_at, dark=True),
        "selection": selection_effect(meals, by_slot, window, val_at),
        "daily_days": _daily_days_dual(times, gluc, base, basal, dark_charts,
                                events=events,
                                tdd=ns["tdd"] if ns else None) if daily else [],
        "curve_cap": curve_cap,
        "slots": [] if lite else _slots_context(by_slot, meals, window, val_at, stability, selected),
        "meals": _meals_context(rows),
        "cr_note": build_cr_note(rows, by_slot), "clean_note": clean_note,
        "slot_defs": slot_definitions(),
        "recs": recs, "cr_example": cr_example,
        "fb": "—" if basal is None else f"{basal[3]:.2f}",
        "fb_lo": "—" if basal is None else f"{basal[4]:.2f}",
        "fb_hi": "—" if basal is None else f"{basal[5]:.2f}",
        "fb_spread": False if basal is None else (
            (basal[5] - basal[4]) >= 0.3 * basal[3] if basal[3] > 0 else False),
        "rest": None if (lite or basal is None) else loop_rest(basal, meals),
        "wlab": wlab, "unit": glucose_unit(),
        "tir_lo": fmt_glucose(g(70)), "tir_hi": fmt_glucose(g(180)),
        "bg70": fmt_glucose(g(70)), "bg54": fmt_glucose(g(54)), "bg140": fmt_glucose(g(140)),
    }


def render(context, template_dir):
    """Render the template with the context and return HTML."""
    env = Environment(loader=FileSystemLoader(str(template_dir)),
                      extensions=["jinja2.ext.i18n"],
                      autoescape=select_autoescape(["html", "j2"]))
    env.install_gettext_translations(_TRANSLATION.get(), newstyle=True)  # pylint: disable=no-member
    return env.get_template("report.html.j2").render(**context)


def parse_args():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="AGP + loop-aware CR report from a CamAPS/Glooko export")
    parser.add_argument("export_dir", nargs="?", default=".",
                        help="unpacked export folder (numbered files are merged)")
    parser.add_argument("-o", "--out", default=None,
                        help="output HTML (default: ./<name>_loop-cr-review_<window>.html)")
    parser.add_argument("-w", "--window-hours", type=float, default=4.0,
                        help="postprandial window in hours (default 4.0; e.g. 3, 3.5, 4)")
    parser.add_argument("-t", "--template-dir", default=None,
                        help="folder containing report.html.j2 (default: ./templates next to this script)")
    parser.add_argument("-d", "--daily", action="store_true",
                        help="also output a daily overview (small day profiles per calendar day)")
    parser.add_argument("--dark-charts", action="store_true",
                        help="also render dark-theme copies of the daily overview (AGP/slot charts always have both)")
    parser.add_argument("--slots-profile", default="default",
                        choices=sorted(SLOT_PROFILES),
                        help="built-in time-of-day profile: default, extended (5–11/11–15/15–22), "
                        "with_snacks (adds 9–11 and 15–17); overridden by --slots-file")
    parser.add_argument("--slots-file", default=None,
                        help="custom time-of-day slots from a JSON file instead of a built-in "
                        "profile (see example-data/slots.example.json)")
    parser.add_argument("--lang", default="de", choices=["de", "en"],
                        help="report language (default: de)")
    parser.add_argument("--assume-camaps", action="store_true",
                        help="Nightscout: run the CamAPS CR assessment (off by default)")
    parser.add_argument("--span", action="store_true",
                        help="print CGM date range and exit (no report)")
    parser.add_argument("--from", dest="date_from", default=None,
                        help="first calendar day YYYY-MM-DD (inclusive)")
    parser.add_argument("--to", dest="date_to", default=None,
                        help="last calendar day YYYY-MM-DD (inclusive)")
    return parser.parse_args()


def generate_report(export_dir, *, lang="de", window_hours=4.0,
                    daily=False, dark_charts=False, assume_camaps=False,
                    date_from=None, date_to=None,
                    slots=None, template_dir=None):
    """Analyse an unpacked export and return (html, context).

    Reusable core shared by the CLI and other front-ends (e.g. a web
    service): no output file is written and nothing is printed, the caller
    decides what to do with the returned HTML. Parameters mirror the CLI;
    ``slots`` is an already-validated slots list (see :func:`load_slots_file`)
    or ``None`` for the built-in slots, and ``template_dir`` defaults to the
    bundled ``templates`` folder.

    Raises :class:`LoopCRError` for invalid exports or slot configuration.
    Slot tables, language and glucose unit are ContextVar-local for the
    duration of this call so concurrent front-ends do not leak state.
    """
    setup_i18n(lang)
    window = int(round(window_hours * 60))
    wlab = (f"{int(window_hours)}h" if float(window_hours).is_integer()
            else f"{window_hours:g}h")
    tpl_dir = Path(template_dir) if template_dir else resource_dir() / "templates"
    with _slot_scope(slots):
        context = build_context(Path(export_dir), window, wlab, daily, lang=lang,
                            dark_charts=dark_charts, assume_camaps=assume_camaps,
                            date_from=date_from, date_to=date_to)
        return render(context, tpl_dir), context


def main():
    """Build and write the report (CLI wrapper around generate_report)."""
    for stream in (sys.stdout, sys.stderr):        # Windows console (cp1252) else crashes on '→'
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = parse_args()
    try:
        if args.span:
            info = peek_span(args.export_dir)
            print(f"{info['source']}  {info['from']} .. {info['to']}  ({info['days']} days)")
            return
        if args.slots_file:
            slots = load_slots_file(args.slots_file)
        elif getattr(args, "slots_profile", "default") != "default":
            slots = slots_from_profile(args.slots_profile)
        else:
            slots = None
        html, context = generate_report(
            args.export_dir, lang=args.lang, window_hours=args.window_hours,
            daily=args.daily, dark_charts=args.dark_charts,
            assume_camaps=args.assume_camaps,
            date_from=parse_day(args.date_from), date_to=parse_day(args.date_to),
            slots=slots, template_dir=args.template_dir)
    except LoopCRError as exc:
        print(str(exc) or "error", file=sys.stderr)
        sys.exit(1)

    wlab = (f"{int(args.window_hours)}h" if float(args.window_hours).is_integer()
            else f"{args.window_hours:g}h")
    slug = re.sub(r"[^a-z0-9]+", "_", context["name"].lower()).strip("_") or "patient"
    out = Path(args.out) if args.out else Path(f"{slug}_loop-cr-review_{wlab}.html")
    out.write_text(html, encoding="utf-8")
    print(f"written: {out} | {len(html)} bytes")
    # Labels from the report context (slot scope already restored)
    if not context.get("lite"):
        print(" | ".join(f"{s['label']}={s['flag']}" for s in context["slots"]))


if __name__ == "__main__":
    main()
