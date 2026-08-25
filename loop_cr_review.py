#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""AGP + loop-aware CR report from a CamAPS/Glooko export.

Separates logic (this module) from presentation (report_template.html.j2). Reads CGM,
bolus and basal data, computes consensus metrics plus a loop-aware CR assessment
per time-of-day slot and renders a self-contained HTML report.
"""
import argparse
import re
import sys
import warnings
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Re-exported so callers keep importing from loop_cr_review: the split into
# lcr/ is internal, the public entry point does not move.
from lcr.common import (  # pylint: disable=unused-import
    BOOTSTRAP_N, BOOTSTRAP_SEED, CR_DEV_HIGH, CR_DEV_LOW, D4_HIGH, D4_STRONG, D4_WEAK,
    DAILY_BOLUS_Y, DAILY_CARB_Y, DAILY_MIN_GAP, DAILY_ROW, DEFAULT_SLOTS, FASTING_HOURS,
    FEW_DAYS_HINT, HYPO_BG, LOOP_RATIO, LoopCRError, MAX_GAP_MIN, MEAL_MIN_CHO, MERGE_SEC,
    MGDL_PER_MMOL, MIN_CLEAN_MEALS, MIN_DAYS_FOR_STABILITY, MIN_MEALS_FOR_STABILITY,
    NADIR_LATE, NADIR_LOW, N_, PEAK_EARLY, PEAK_RISE_HIGH, PRE_BG_HIGH, REPO_URL,
    REST_EXCL_AFTER_MEAL_MIN, REST_MIN_HOURS, REST_MIN_WINDOWS, REST_MIN_WINDOW_MIN,
    REST_OFF_FRAC, REST_REL, SLOT_PROFILES, STABILITY_HIGH, STABILITY_MODERATE, TIME_FMTS,
    TOOL_NAME, WEEKDAYS, _, _GLUCOSE_UNIT, _SLOTS_VAR, _SLOT_PALETTE, _TRANSLATION,
    _basal_from_segments, _default_slot_state, _derive_slot_globals, _slot_norm_rows,
    _slot_scope, _slot_state, build_slots, current_translation, fmt_cr, fmt_delta,
    fmt_glucose, g, glucose_unit, is_mmol, load_slots_file, merge_carb_entries, num,
    parse_ts, resource_dir, select_slot_rows, set_glucose_unit, setup_i18n,
    slot_median_curve, slot_norm_bands, slot_norm_curve, slot_of, slots_from_profile,
    sorted_unique_series, tool_version)
from lcr.readers import (  # pylint: disable=unused-import
    _nightscout_dir, _ns_offset_minutes, _ns_parse_time, clip_by_days, is_libreview,
    is_nightscout, libreview_csv, numbered_csvs, parse_day, peek_span, read_basal_timeline,
    read_bolus_events, read_cgm, read_libreview, read_meals, read_nightscout, read_tdd)
from lcr.charts import (  # pylint: disable=unused-import
    _chart_palette, _chart_theme, _day_title, _draw_day_events, agp_chart, daily_charts,
    fig_to_b64, gri_grid_chart, selection_effect, slot_curves_chart, slot_norm_curves_chart)

# --- Analysis ---------------------------------------------------------
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


def gri_metrics(met):
    """Glycemia Risk Index (GRI) and its two actionable components."""
    hypo = met["tbr2"] + 0.8 * met["tbr1"]
    hyper = met["tar2"] + 0.5 * met["tar1"]
    score = min(100.0, 3.0 * hypo + 1.6 * hyper)
    if score <= 20:
        zone, zrange, risk = "A", "0–20", _("Low risk")
    elif score <= 40:
        zone, zrange, risk = "B", "21–40", _("Low to moderate risk")
    elif score <= 60:
        zone, zrange, risk = "C", "41–60", _("Moderate risk")
    elif score <= 80:
        zone, zrange, risk = "D", "61–80", _("High risk")
    else:
        zone, zrange, risk = "E", "81–100", _("Very high risk")
    return {
        "score": score, "zone": zone, "range": zrange, "risk": risk,
        "hypo": hypo, "hyper": hyper,
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
    cgm_times64 = (np.asarray(cgm_times, dtype="datetime64[ns]")
                   if cgm_times is not None else None)
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
        cgm_gap = cgm_gap_in_window(start, window, cgm_times64) if cgm_times64 is not None else False
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

    # Keep the exact day-clustered bootstrap, but do the resamples in NumPy.
    # Padding each day with NaN means nanmedian over the day/meal axes is the
    # same statistic as concatenating the selected day blocks.
    max_per_day = max(len(rows) for rows in days)
    def day_matrix(key):
        out = np.full((len(days), max_per_day), np.nan, dtype=float)
        for i, rows in enumerate(days):
            out[i, :len(rows)] = [r[key] for r in rows]
        return out

    exc = day_matrix("exc")
    bol = day_matrix("bolus")
    d4v = day_matrix("d4")
    cre = day_matrix("cr_eff")

    rng = np.random.default_rng(seed)                   # fixed: reports stay reproducible
    pick = rng.integers(0, len(days), size=(n_boot, len(days)))
    with warnings.catch_warnings():                     # all-NaN slices are expected
        warnings.simplefilter("ignore", RuntimeWarning)
        m_exc = np.nanmedian(exc[pick], axis=(1, 2))
        m_bol = np.nanmedian(bol[pick], axis=(1, 2))
        m_d4 = np.nanmedian(d4v[pick], axis=(1, 2))
        m_cre = np.nanmedian(cre[pick], axis=(1, 2))

        cls = verdict_class(float(np.nanmedian(exc)), float(np.nanmedian(bol)),
                            float(np.nanmedian(d4v)))
        classes = np.array([verdict_class(e, b, d) for e, b, d
                            in zip(m_exc, m_bol, m_d4)])
        counts = {name: int(np.count_nonzero(classes == name))
                  for name in ("weak", "ok", "strong")}
        ratio_boot = np.divide(m_exc, m_bol,
                               out=np.full_like(m_exc, np.nan), where=m_bol != 0)
        spread = {}
        for key, vals in (("cre", m_cre), ("ratio", ratio_boot)):
            if not np.all(np.isnan(vals)):
                spread[key] = tuple(np.nanpercentile(vals, [2.5, 97.5]))
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


# --- Context / Rendering ----------------------------------------------------


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
    cgm_times64 = (np.asarray(times, dtype="datetime64[ns]")
                   if times is not None else None)

    met = consensus_metrics(times, gluc)
    gri = gri_metrics(met)
    if basal is None and not lite:
        raise LoopCRError("No basal rates found.")
    rows = [] if basal is None else analyze_meals(
        meals, minors, basal, window, val_at, cgm_times=cgm_times64)
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
            "cgm_gap": cgm_gap_in_window(meal["time"], window, cgm_times64) if cgm_times64 is not None else False,
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
        "gri": {**gri,
                "img": gri_grid_chart(gri, dark=False),
                "img_dark": gri_grid_chart(gri, dark=True) if dark_charts else ""},
        "tir_bands": [{"label": lab, "val": f"{val:.1f}", "width": f"{min(val, 100):.1f}",
                       "color": col} for lab, val, col in _tir_bands(met)],
        "agp_img": agp_chart(times, gluc),
        "agp_img_dark": agp_chart(times, gluc, dark=True) if dark_charts else "",
        "slot_img": slot_curves_chart(meals, window, val_at),
        "slot_img_dark": (slot_curves_chart(meals, window, val_at, dark=True)
                          if dark_charts else ""),
        "slot_norm_img": slot_norm_curves_chart(meals, window, val_at),
        "slot_norm_img_dark": (slot_norm_curves_chart(meals, window, val_at, dark=True)
                               if dark_charts else ""),
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
                        help="also render dark-theme chart PNGs (AGP, slot curves, baseline-norm, "
                        "and daily if -d); without this, only light charts are embedded")
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
