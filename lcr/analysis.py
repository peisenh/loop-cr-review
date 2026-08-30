# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The method itself: meal windows, loop extra basal, CR_eff, verdicts.

This is what the project is about — everything else reads data, draws
pictures or arranges them. Kept free of rendering so a change to the report
cannot quietly change a verdict.
"""
import html
import warnings
from datetime import timedelta

import numpy as np

from lcr.common import (
    BOOTSTRAP_N, BOOTSTRAP_SEED, CR_DEV_HIGH, CR_DEV_LOW, D4_HIGH, D4_STRONG, FASTING_HOURS,
    HYPO_BG, LOOP_RATIO, MAX_GAP_MIN, MGDL_PER_MMOL, MIN_DAYS_FOR_STABILITY,
    MIN_MEALS_FOR_STABILITY, NADIR_LATE, NADIR_LOW, PEAK_EARLY, PEAK_RISE_HIGH,
    PRE_BG_HIGH, REST_EXCL_AFTER_MEAL_MIN, REST_MIN_HOURS, REST_MIN_WINDOWS,
    REST_MIN_WINDOW_MIN, REST_OFF_FRAC, REST_REL, STABILITY_HIGH, STABILITY_MODERATE, _,
    _slot_state, fmt_cr, g, glucose_unit, is_mmol, select_slot_rows, slot_of)

__all__ = [
    "consensus_metrics",
    "gri_metrics",
    "make_glucose_lookup",
    "cgm_gap_in_window",
    "_scan_minors",
    "analyze_meals",
    "verdict_class",
    "observed_range",
    "decision_stability",
    "aggregate_slot",
    "shape_description",
    "curve_metrics",
    "_weak_levers",
    "_hypo_caution",
    "slot_levers",
    "_reference_lever",
    "slot_headline",
    "build_cr_note",
    "loop_rest",
]

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

    basal: (rate, t0, minutes, fasting, fasting_lo, fasting_hi) from
    read_basal_timeline, or None for sources that carry no basal rate. Without it
    the loop extra basal and CR_eff are nan; everything the glucose curve alone
    can say - the return delta, contamination, hypo rescues, CGM gaps - is worked
    out just the same.
    minors: small carb entries (snacks / hypo rescues) below the meal bar. A minor
    inside a meal's window contaminates it; a minor with no bolus at low glucose is
    treated as a hypo rescue, which additionally sets a hypo flag on the meal.
    cgm_times: CGM timestamps for :func:`cgm_gap_in_window` (optional; gap=False if omitted).
    """
    rate, t0, minutes, fasting = basal[:4] if basal else (None, None, None, None)
    meal_times = [m["time"] for m in meals]
    cgm_times64 = (np.asarray(cgm_times, dtype="datetime64[ns]")
                   if cgm_times is not None else None)
    rows = []
    for meal in meals:
        start = meal["time"]
        # A meal the basal trace does not cover is still a meal: it keeps its
        # glucose course and counts towards the verdict, only the loop figures
        # stay empty. Dropping it would silently shrink the sample.
        i0, covered = 0, False
        if basal:
            i0 = int((start - t0).total_seconds() // 60)
            covered = 0 <= i0 and i0 + window < minutes
        contam = any(0 < (o - start).total_seconds() <= window * 60
                     for o in meal_times if o != start)
        minor_contam, hypo_rescue = _scan_minors(start, window, minors, val_at)
        contam = contam or minor_contam
        cgm_gap = cgm_gap_in_window(start, window, cgm_times64) if cgm_times64 is not None else False
        excess = (float(np.sum(rate[i0:i0 + window] - fasting) / 60.0)
                  if covered else np.nan)
        pre, post = val_at(start, 0), val_at(start, window)
        total = meal["bolus"] + excess if covered else np.nan
        rows.append({
            "slot": slot_of(start.hour), "time": start, "cho": meal["cho"],
            "bg": meal["bg"], "bolus": meal["bolus"], "pre": pre,
            "cr": meal["cho"] / meal["bolus"] if meal["bolus"] else np.nan,
            "exc": excess,
            "cr_eff": meal["cho"] / total if covered and total > 0 else np.nan,
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
            _("underdosed → tighten CR, rough direction CR_eff %(cre)s") % {"cre": fmt_cr(agg["cre"])}
            if not np.isnan(agg["cre"])
            # Without a basal trace there is no CR_eff to point at; the direction
            # is all that is left, and naming an em dash would only puzzle.
            else _("underdosed → tighten CR; decide the size with the care team"))]
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
        # The curve did not really drop, so the verdict came from somewhere else.
        # Only claim throttling when the extra basal actually is negative - saying
        # it while the loop added insulin is the contradiction a reader spots
        # immediately against the daily charts.
        if not np.isnan(agg["exc"]) and agg["exc"] < 0:
            return _("returns close to baseline, loop throttles noticeably")
        return _("returns close to baseline")
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
        if np.isnan(med_cr):
            # No meal with a bolus at all: there is no median to talk about.
            return ""
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
                     % {"slot": html.escape(_slot_state()[2][slot], quote=True),
                        "scr": scr, "dir": direction,
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
