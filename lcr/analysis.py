# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The method itself: meal windows, loop extra basal, CR_eff, verdicts.

This is what the project is about — everything else reads data, draws
pictures or arranges them. Kept free of rendering so a change to the report
cannot quietly change a verdict.
"""
import html
from datetime import timedelta

import math

from lcr import pcg64, pure

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
    mean, sd = float(pure.mean(gluc)), float(pure.stdev(gluc))
    days = (times[-1] - times[0]).total_seconds() / 86400
    step = pure.median(pure.diff([t.timestamp() for t in times])) / 60
    mean_mgdl = mean * MGDL_PER_MMOL if is_mmol() else mean

    def share(test):
        """Percentage of readings the test holds for. -> float

        The array version took the mean of a boolean vector; counting says the
        same thing about a list, and says it more plainly.
        """
        return 100.0 * sum(1 for v in gluc if test(v)) / len(gluc)

    return {
        "mean": mean, "cv": sd / mean * 100, "days": days,
        # Both units of the GMI, from the same paper (Bergenstal 2018). Which
        # one a clinic speaks follows its HbA1c convention, not the glucose one:
        # per cent under DCCT/NGSP, mmol/mol under IFCC. Reporting both saves
        # guessing, and the reader takes the one they know.
        "gmi": 3.31 + 0.02392 * mean_mgdl,
        "gmi_mmol": 12.71 + 4.70587 * (mean_mgdl / MGDL_PER_MMOL),
        "wear": 100 * len(gluc) / (days * 24 * 60 / step) if step else float("nan"),
        "tir": share(lambda v: g(70) <= v <= g(180)),
        "titr": share(lambda v: g(70) <= v <= g(140)),
        "tbr1": share(lambda v: g(54) <= v < g(70)),
        "tbr2": share(lambda v: v < g(54)),
        "tar1": share(lambda v: g(180) < v <= g(250)),
        "tar2": share(lambda v: v > g(250)),
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
    # datetime64 was only ever a way to binary-search a sorted trace; plain
    # datetimes compare and search the same way.
    stamps = list(times)
    values = [float(v) for v in gluc]

    def val_at(ref, minutes, tol=12):
        lo = ref + timedelta(minutes=minutes - tol)
        hi = ref + timedelta(minutes=minutes + tol)
        i = pure.searchsorted(stamps, lo, side="left")
        j = pure.searchsorted(stamps, hi, side="right")
        if j <= i:
            return pure.NAN
        return float(pure.mean(values[i:j]))
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
    stamps = list(times)
    i = pure.searchsorted(stamps, start, side="left")
    j = pure.searchsorted(stamps, end, side="right")
    if j <= i:
        return True
    limit = timedelta(minutes=int(max_gap_min))
    win = stamps[i:j]
    if win[0] - start > limit:
        return True
    if end - win[-1] > limit:
        return True
    if len(win) > 1 and any(b - a > limit for a, b in zip(win, win[1:])):
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
            if minor["bolus"] <= 0 and not pure.is_nan(g_now) and g_now < g(HYPO_BG):
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
    cgm_stamps = list(cgm_times) if cgm_times is not None else None
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
        cgm_gap = cgm_gap_in_window(start, window, cgm_stamps) if cgm_stamps is not None else False
        # The rate is a list of U/h per minute; the integral over the window
        # is the sum of the differences to the fasting rate, in hours.
        excess = (math.fsum(v - fasting for v in rate[i0:i0 + window]) / 60.0
                  if covered else pure.NAN)
        pre, post = val_at(start, 0), val_at(start, window)
        total = meal["bolus"] + excess if covered else pure.NAN
        rows.append({
            "slot": slot_of(start.hour), "time": start, "cho": meal["cho"],
            "bg": meal["bg"], "bolus": meal["bolus"], "pre": pre,
            "cr": meal["cho"] / meal["bolus"] if meal["bolus"] else pure.NAN,
            "exc": excess,
            "cr_eff": meal["cho"] / total if covered and total > 0 else pure.NAN,
            "d4": (post - pre) if not pure.is_nan(post) and not pure.is_nan(pre) else pure.NAN,
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
    vals = [r[key] for r in use_rows if not pure.is_nan(r[key])]
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

    # The same day-clustered bootstrap as before. The padding the array version
    # needed is gone with it: a resample is the values of the picked days laid
    # end to end, and a median ignores what is not there.
    def per_day(key):
        return [[row[key] for row in rows] for rows in days]

    exc = per_day("exc")
    bol = per_day("bolus")
    d4v = per_day("d4")
    cre = per_day("cr_eff")

    def flat(block):
        return [v for day in block for v in day]

    # numpy's generator, reproduced: another stream would give a statistically
    # equivalent answer and a different printed one.
    rng = pcg64.default_rng(seed)                       # fixed: reports stay reproducible
    counts = {"weak": 0, "ok": 0, "strong": 0}
    m_cre, ratio_boot = [], []
    for _ in range(n_boot):
        picks = rng.integers(0, len(days), len(days))
        med_exc = pure.nanmedian([v for i in picks for v in exc[i]])
        med_bol = pure.nanmedian([v for i in picks for v in bol[i]])
        med_d4 = pure.nanmedian([v for i in picks for v in d4v[i]])
        m_cre.append(pure.nanmedian([v for i in picks for v in cre[i]]))
        ratio_boot.append(med_exc / med_bol if med_bol else pure.NAN)
        counts[verdict_class(med_exc, med_bol, med_d4)] += 1

    cls = verdict_class(float(pure.nanmedian(flat(exc))),
                        float(pure.nanmedian(flat(bol))),
                        float(pure.nanmedian(flat(d4v))))
    spread = {}
    for key, vals in (("cre", m_cre), ("ratio", ratio_boot)):
        if not all(pure.is_nan(v) for v in vals):
            spread[key] = (pure.percentile(vals, 2.5), pure.percentile(vals, 97.5))
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
        vals = [r[key] for r in use if not pure.is_nan(r[key])]
        return float(pure.nanmedian(vals)) if vals else pure.NAN

    exc, bol, d4 = med("exc"), med("bolus"), med("d4")
    rescues = sum(1 for r in slot_rows if r.get("hypo_rescue"))
    cls = verdict_class(exc, bol, d4)
    flag = {"weak": _("coverage looks too weak"),
            "strong": _("coverage looks too strong"),
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
    if curve is None or all(pure.is_nan(v) for v in curve):
        return None
    start, end, low = pure.nanmedian(curve[:2]), pure.nanmedian(curve[-2:]), pure.nanmin(curve)
    if low < 75:
        return _("rises and then falls to low values")
    if end - start > g(25):
        return _("climbs and does not return to baseline")
    if end - start < -g(25):
        return _("falls clearly below baseline")
    return _("returns close to baseline (balanced)")


def curve_metrics(curve, grid):
    """Peak/nadir/start/end + 'still rising at the end' from a postprandial curve."""
    pk, nd = int(pure.nanargmax(curve)), int(pure.nanargmin(curve))
    return {"start": float(pure.nanmedian(curve[:2])), "end": float(pure.nanmedian(curve[-2:])),
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
            _("underdosed; CR_eff came out at %(cre)s here") % {"cre": fmt_cr(agg["cre"])}
            if not pure.is_nan(agg["cre"])
            # Without a basal trace there is no CR_eff to point at; the direction
            # is all that is left, and naming an em dash would only puzzle.
            else _("underdosed; a topic for the care team"))]
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
      - no rescue (curve hypo only) -> preventive "the hypo risk shapes this window"
      - rescue + too strong / systematic -> a treated hypo, reduce the dose here
      - rescue + otherwise (weak / isolated-in-ok) -> a treated hypo on one meal,
        check that meal rather than tightening the whole slot.
    """
    base = {"n": met["nadir"], "t": met["nadir_t"], "u": glucose_unit()}
    if not agg.get("rescues"):
        return (_("Caution"), "obs", _("nadir ~%(n).0f %(u)s around %(t)d min "
                                       "— the hypo risk shapes this window") % base)
    reduce_dose = agg["cls"] == "strong" or agg.get("systematic")
    if curve_hypo:
        if reduce_dose:
            return (_("Caution"), "obs", _("nadir ~%(n).0f %(u)s around %(t)d min — a hypo "
                                           "occurred and was treated; the dose in "
                                           "this window is worth discussing") % base)
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
        levers.append((_("Pre-bolus"), "sea", _("early high peak — a longer bolus-meal interval is one possible "
                                                  "explanation (it caps the spike without more dose)")))
    if agg["cls"] == "weak":
        levers.extend(_weak_levers(agg, window))
    elif agg["cls"] == "strong":
        levers.append((_("Dose"), "cr", _("overdosed/drop — the dose of this meal is the nearest candidate; "
                                           "consider pre-bolus and dose together")))
    late_rise = met["peak_t"] >= window * 0.66 and met["end"] - met["start"] > 20
    if late_rise and agg["cls"] != "ok":
        levers.append((_("Fat/protein"), "fp", _("monotonic late rise (no turning "
                                                 "point) — fat/protein comes into "
                                                 "question; "
                                                   "a split or extended bolus is as much in question as the ratio")))
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
        return (_("Reference"), "obs", _("the dose fits; for timing see the "
                                         "pre-bolus note above"))
    return (_("Reference"), "obs", _("dose and timing fit; this slot "
                                     "serves as a comparison for the others"))


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
        if not pure.is_nan(agg["exc"]) and agg["exc"] < 0:
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
    all_cr = [r["cr"] for r in rows if not pure.is_nan(r["cr"])]
    med_cr = float(pure.median(all_cr)) if all_cr else float("nan")
    dev = []
    for slot in _slot_state()[1]:
        srows = by_slot.get(slot, [])
        if len(srows) < 3:
            continue
        scr = float(pure.nanmedian([r["cr"] for r in srows]))
        pres = [r["pre"] for r in srows if not pure.is_nan(r["pre"])]
        spre = float(pure.nanmedian(pres)) if pres else float("nan")
        if not pure.is_nan(scr) and (scr < CR_DEV_LOW * med_cr or scr > CR_DEV_HIGH * med_cr):
            dev.append((slot, scr, spre))
    if not dev:
        if pure.is_nan(med_cr):
            # No meal with a bolus at all: there is no median to talk about.
            return ""
        return _("• Derived CR = CHO/bolus; no slot deviates notably from the median "
                 "(1:%(m).1f).<br>") % {"m": med_cr}
    parts = []
    for slot, scr, spre in dev:
        direction = _("tighter") if scr < med_cr else _("looser")
        if not pure.is_nan(spre) and spre > g(PRE_BG_HIGH):
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
    blocked = [False] * minutes
    for i in range(minutes):
        if (t0 + timedelta(minutes=i)).hour in FASTING_HOURS:
            blocked[i] = True
    for m in meals:
        i0 = int((m["time"] - t0).total_seconds() // 60)
        a = max(0, i0)
        b = min(minutes, i0 + REST_EXCL_AFTER_MEAL_MIN)
        if b > a:
            # A list slice takes a sequence, not a scalar the way an array did.
            blocked[a:b] = [True] * (b - a)
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
            mean_r = float(pure.mean(sl))
            rel = (mean_r / fasting) - 1.0
            # Share of minutes far enough off the fasting rate: a mean over
            # booleans, which is what the array comparison produced.
            off = sum(1 for v in sl if abs(v / fasting - 1.0) >= REST_REL) / len(sl)
            extra_u = math.fsum(v - fasting for v in sl) / 60.0
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
        rel = float(pure.median([abs(w["rel"]) for w in windows]))
        off = float(pure.median([w["off"] for w in windows]))
        state = "active" if (rel >= REST_REL or off >= REST_OFF_FRAC) else "quiet"
    return {"state": state, "windows": n, "hours": hours, "rel": rel, "off": off}
