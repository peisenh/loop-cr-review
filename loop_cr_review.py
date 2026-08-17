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
from collections import defaultdict
from datetime import datetime, timedelta
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
_SLOT_PALETTE = ("#c0392b", "#e0913a", "#3a9b46", "#2c6fbb", "#8e44ad", "#16a085")


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
        raise LoopCRError(f"{source}: erwarte eine nicht-leere Liste von Slot-Objekten.")
    slots, seen_keys, catchall = [], set(), 0
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise LoopCRError(f"{source}, Eintrag {i}: erwarte ein Objekt (key/label/start/end).")
        missing = [f for f in ("key", "label", "start", "end") if f not in entry]
        if missing:
            raise LoopCRError(f"{source}, Eintrag {i}: fehlende Felder {missing}.")
        key, label, start, end = entry["key"], entry["label"], entry["start"], entry["end"]
        if key in seen_keys:
            raise LoopCRError(f"{source}: doppelter key '{key}'.")
        seen_keys.add(key)
        if (not isinstance(start, int) or not isinstance(end, int)
                or isinstance(start, bool) or isinstance(end, bool)):
            raise LoopCRError(f"{source}, '{key}': start/end muss eine ganze Zahl sein.")
        if start == -1 and end == -1:
            catchall += 1
        elif not (0 <= start < 24 and 0 < end <= 24 and start < end):
            raise LoopCRError(f"{source}, '{key}': start/end muss 0<=start<end<=24 "
                     "sein (oder beide -1 fuer den Auffangbecken-Slot).")
        slots.append((key, label, start, end))
    if catchall != 1:
        raise LoopCRError(f"{source}: genau ein Auffangbecken-Eintrag (start=-1, end=-1) "
                 f"noetig, gefunden: {catchall}.")
    return slots


def load_slots_file(path):
    """Load custom slot time windows from a JSON file (list of objects).

    Expected: [{"key": "...", "label": "...", "start": H, "end": H}, ...].
    Validation is delegated to :func:`build_slots`.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LoopCRError(f"Slots-Datei '{path}' nicht lesbar/kein gueltiges JSON: {exc}")
    return build_slots(raw, f"Slots-Datei '{path}'")
FASTING_HOURS = (0, 1, 2, 3, 4, 5)
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
        raise LoopCRError(f"Keine Basalraten in {base / 'Insulin data'} gefunden "
                 "(basal_data_*.csv leer oder fehlt).")
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
    """Closure: median glucose ~minutes after ref (+-tol)."""
    def val_at(ref, minutes, tol=12):
        lo, hi = ref + timedelta(minutes=minutes - tol), ref + timedelta(minutes=minutes + tol)
        mask = (times >= lo) & (times <= hi)
        return float(gluc[mask].mean()) if mask.any() else np.nan
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
    in_win = [t for t in times if start <= t <= end]
    if not in_win:
        return True
    points = [start, *in_win, end]
    limit_sec = float(max_gap_min) * 60.0
    for a, b in zip(points, points[1:]):
        if (b - a).total_seconds() > limit_sec:
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


def aggregate_slot(slot_rows):
    """Median aggregation of a slot + verdict. -> dict or None."""
    use, n_clean, used_clean_only = select_slot_rows(slot_rows)
    if not use:
        return None
    low_confidence = not used_clean_only     # verdict relies (also) on contaminated meals

    def med(key):
        return float(np.nanmedian([r[key] for r in use if not np.isnan(r[key])]))

    exc, bol, d4 = med("exc"), med("bolus"), med("d4")
    rescues = sum(1 for r in slot_rows if r.get("hypo_rescue"))
    ratio = exc / bol if bol else 0
    if ratio > LOOP_RATIO or d4 > g(D4_HIGH):
        flag, cls = _("too weak → tighten"), "weak"
    elif ratio < -LOOP_RATIO or d4 < g(D4_STRONG):
        flag, cls = _("too strong → loosen"), "strong"
    else:
        flag, cls = _("plausibly adequate"), "ok"
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
    return (np.nanmedian(np.array(rows), axis=0) if rows else None), len(rows)


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



def slot_norm_curves_chart(meals, window, val_at, by_slot, dark=False):
    """Baseline-normalised median curves per slot as base64 PNG (light or dark)."""
    grid = np.arange(0, window + 1, 10)
    with _chart_theme(dark):
        fig, ax = plt.subplots(figsize=(10, 3.6))
        ax.axhline(0, color="#888", lw=.8)
        for slot in _slot_state()[1]:
            clean_times = None
            if by_slot is not None:
                use, _n, only = select_slot_rows(by_slot.get(slot, []))
                if only:
                    clean_times = {r["time"] for r in use}
            curve, n = slot_norm_curve(meals, slot, window, val_at, clean_times)
            if curve is not None:
                basis = "clean" if clean_times is not None else "alle"
                ax.plot(grid, curve, color=_slot_state()[3][slot], lw=2,
                        label=f"{_slot_state()[2][slot]} (n={n}, {basis})")
        ax.set_xlim(0, window)
        ax.set_xlabel(_("Minutes after meal"))
        ax.set_ylabel(_("Δ %(u)s vs. meal start") % {"u": glucose_unit()})
        if ax.get_legend_handles_labels()[1]:
            ax.legend(fontsize=8)
        ax.grid(alpha=.25)
        return fig_to_b64(fig)



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
    """One page-wide panel per day (CGM + bolus/carb + basal + TDD), oldest first."""
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
    out = []
    for _key, label, start, end in _slot_state()[0]:
        if start < 0:
            out.append(_("%(label)s = everything outside the other windows") % {"label": label})
        else:
            out.append(f"{label} = {start:02d}:00–{end:02d}:00 Uhr")
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


def _slots_context(by_slot, meals, window, val_at):
    out = []
    for slot, _label, _start, _end in _slot_state()[0]:
        agg = aggregate_slot(by_slot.get(slot, []))
        if not agg:
            continue
        out.append({
            "label": _slot_state()[2][slot], "n": agg["n"], "clean": agg["clean"],
            "cho": f"{agg['cho']:.0f}", "cr": fmt_cr(agg["cr"]), "bol": f"{agg['bol']:.1f}",
            "exc": f"{agg['exc']:+.2f}", "cre": fmt_cr(agg["cre"]), "d4": fmt_delta(agg["d4"]),
            "flag": _slot_flag(agg, slot, meals, window, val_at), "cls": agg["cls"],
        })
    return out


def _meals_context(rows):
    out = []
    for row in sorted(rows, key=lambda r: r["time"]):
        cls = ""
        if not np.isnan(row["d4"]):
            weak = (row["exc"] / row["bolus"] if row["bolus"] else 0) > LOOP_RATIO and row["d4"] > g(D4_WEAK)
            cls = "strong" if row["d4"] < g(D4_STRONG) else "weak" if weak else ""
        out.append({
            "time": f"{row['time']:%d.%m %H:%M}", "label": _slot_state()[2][row["slot"]],
            "cho": f"{row['cho']:.0f}", "bolus": f"{row['bolus']:.1f}", "cr": fmt_cr(row["cr"]),
            "exc": f"{row['exc']:+.2f}", "cre": fmt_cr(row["cr_eff"]),
            "d4": fmt_delta(row["d4"]) if not np.isnan(row["d4"]) else "—",
            "contam": row["contam"], "hypo_rescue": row.get("hypo_rescue", False),
            "cgm_gap": row.get("cgm_gap", False),
            "cls": cls,
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


def _recommendations_context(meals, by_slot, window, val_at):
    """Per slot: curve metrics + derived levers; plus CR_eff example."""
    grid = np.arange(0, window + 1, 10)
    recs, example, example_exc = [], None, 0.0
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



def _daily_days_dual(times, gluc, base, basal):
    """Light + dark daily panels in one list for the single HTML report."""
    events = read_bolus_events(base)
    tdd = read_tdd(base)
    light = daily_charts(times, gluc, events, basal, tdd, dark=False)
    dark = daily_charts(times, gluc, events, basal, tdd, dark=True)
    return [{"img": a["img"], "img_dark": b["img"]} for a, b in zip(light, dark)]


def build_context(base, window, wlab, daily=False):
    """Read all data, analyse, and assemble the template context."""
    times, gluc, name, sensor = read_cgm(base)
    meals, minors, pump = read_meals(base)
    basal = read_basal_timeline(base)
    val_at = make_glucose_lookup(times, gluc)

    met = consensus_metrics(times, gluc)
    rows = analyze_meals(meals, minors, basal, window, val_at, cgm_times=times)
    by_slot = defaultdict(list)
    for row in rows:
        by_slot[row["slot"]].append(row)
    curve_cap, clean_note = _captions(meals, by_slot, window, val_at)
    recs, cr_example = _recommendations_context(meals, by_slot, window, val_at)
    device = " · ".join(p for p in (pump, sensor) if p) or _("device unknown")

    return {
        "tool": TOOL_NAME, "name": name, "span": f"{times[0]:%d.%m.%Y}–{times[-1]:%d.%m.%Y}",
        "generated": datetime.now().strftime("%d.%m.%Y, %H:%M"), "repo": REPO_URL,
        "version": tool_version(),
        "days": f"{met['days']:.0f}", "device": f"{device} · Auto Mode",
        "wear": f"{met['wear']:.0f}", "mean": fmt_glucose(met["mean"]), "gmi": f"{met['gmi']:.1f}",
        "cv": f"{met['cv']:.0f}", "tir": f"{met['tir']:.0f}", "titr": f"{met['titr']:.0f}",
        "tir_bands": [{"label": lab, "val": f"{val:.1f}", "width": f"{min(val, 100):.1f}",
                       "color": col} for lab, val, col in _tir_bands(met)],
        "agp_img": agp_chart(times, gluc), "agp_img_dark": agp_chart(times, gluc, dark=True),
        "slot_img": slot_curves_chart(meals, window, val_at),
        "slot_img_dark": slot_curves_chart(meals, window, val_at, dark=True),
        "slot_norm_img": slot_norm_curves_chart(meals, window, val_at, by_slot),
        "slot_norm_img_dark": slot_norm_curves_chart(meals, window, val_at, by_slot, dark=True),
        "daily_days": _daily_days_dual(times, gluc, base, basal) if daily else [],
        "curve_cap": curve_cap, "slots": _slots_context(by_slot, meals, window, val_at),
        "meals": _meals_context(rows),
        "cr_note": build_cr_note(rows, by_slot), "clean_note": clean_note,
        "slot_defs": slot_definitions(),
        "recs": recs, "cr_example": cr_example,
        "fb": f"{basal[3]:.2f}", "fb_lo": f"{basal[4]:.2f}", "fb_hi": f"{basal[5]:.2f}",
        # strongly varying if the range of the nightly means is at least 30%
        # of the overall mean. Absolute range (not factor hi/lo),
        # so that nights with a mean of 0.00 (fully suspended) are also captured
        # correctly -- a factor would be undefined there.
        "fb_spread": (basal[5] - basal[4]) >= 0.3 * basal[3] if basal[3] > 0 else False,
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
    parser.add_argument("--slots-file", default=None,
                        help="custom time-of-day slots from a JSON file instead of the built-in "
                        "breakfast/lunch/dinner/other (see example-data/slots.example.json)")
    parser.add_argument("--lang", default="de", choices=["de", "en"],
                        help="report language (default: de)")
    return parser.parse_args()


def generate_report(export_dir, *, lang="de", window_hours=4.0,
                    daily=False, slots=None, template_dir=None):
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
        context = build_context(Path(export_dir), window, wlab, daily)
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
        slots = load_slots_file(args.slots_file) if args.slots_file else None
        html, context = generate_report(
            args.export_dir, lang=args.lang, window_hours=args.window_hours,
            daily=args.daily, slots=slots, template_dir=args.template_dir)
    except LoopCRError as exc:
        print(str(exc) or "error", file=sys.stderr)
        sys.exit(1)

    wlab = (f"{int(args.window_hours)}h" if float(args.window_hours).is_integer()
            else f"{args.window_hours:g}h")
    slug = re.sub(r"[^a-z0-9]+", "_", context["name"].lower()).strip("_") or "patient"
    out = Path(args.out) if args.out else Path(f"{slug}_loop-cr-review_{wlab}.html")
    out.write_text(html, encoding="utf-8")
    print(f"geschrieben: {out} | {len(html)} bytes")
    # Labels from the report context (slot scope already restored)
    print(" | ".join(f"{s['label']}={s['flag']}" for s in context["slots"]))


if __name__ == "__main__":
    main()
