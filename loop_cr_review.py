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
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

# Re-exported so callers keep importing from loop_cr_review: the split into
# lcr/ is internal, the public entry point does not move.
from lcr.common import (  # pylint: disable=unused-import
    BOOTSTRAP_N, BOOTSTRAP_SEED, CR_DEV_HIGH, CR_DEV_LOW, D4_HIGH, D4_STRONG, D4_WEAK,
    DAILY_BOLUS_Y, DAILY_CARB_Y, DAILY_MIN_GAP, DAILY_ROW, DEFAULT_SLOTS, FASTING_HOURS,
    FEW_DAYS_HINT, HEAD_BYTES, HYPO_BG, LOOP_RATIO, LoopCRError, MAX_GAP_MIN,
    MAX_SEARCH_DEPTH, MAX_SNIFF_FILES, MEAL_MIN_CHO, MERGE_SEC, MGDL_PER_MMOL,
    MIN_CLEAN_MEALS, MIN_DAYS_FOR_STABILITY, MIN_MEALS_FOR_STABILITY, NADIR_LATE, NADIR_LOW,
    N_, PEAK_EARLY, PEAK_RISE_HIGH, PRE_BG_HIGH, REPO_URL, REST_EXCL_AFTER_MEAL_MIN,
    REST_MIN_HOURS, REST_MIN_WINDOWS, REST_MIN_WINDOW_MIN, REST_OFF_FRAC, REST_REL,
    SKIP_DIRS, SLOT_PROFILES, STABILITY_HIGH, STABILITY_MODERATE, TIME_FMTS, TOOL_NAME,
    WEEKDAYS, _, _GLUCOSE_UNIT, _SLOTS_VAR, _SLOT_PALETTE, _TRANSLATION,
    _basal_from_segments, _default_slot_state, _derive_slot_globals, _slot_norm_rows,
    _slot_scope, _slot_state, build_slots, current_translation, find_below, fmt_cr,
    fmt_delta, fmt_glucose, g, glucose_unit, is_mmol, load_slots_file, merge_carb_entries,
    num, parse_ts, resource_dir, select_slot_rows, set_glucose_unit, setup_i18n,
    single_match, slot_median_curve, slot_norm_bands, slot_norm_curve, slot_of,
    slots_from_profile, sniff_candidates, sorted_unique_series, tool_version)
from lcr.readers import (  # pylint: disable=unused-import
    _nightscout_dir, _ns_offset_minutes, _ns_parse_time, clip_by_days, dexcom_csv,
    is_dexcom, is_glooko, is_libreview, is_nightscout, libreview_csv, numbered_csvs,
    parse_day, peek_span, read_basal_timeline, read_bolus_events, read_cgm, read_dexcom,
    read_libreview, read_meals, read_nightscout, read_tdd)
from lcr import pure
from lcr.charts import (  # pylint: disable=unused-import
    PALETTE, _day_title, agp_chart, daily_charts, gri_grid_chart, selection_effect,
    slot_curves_chart, slot_norm_curves_chart)
from lcr.analysis import (  # pylint: disable=unused-import
    _hypo_caution, _reference_lever, _scan_minors, _weak_levers, aggregate_slot,
    analyze_meals, build_cr_note, cgm_gap_in_window, consensus_metrics, curve_metrics,
    decision_stability, gri_metrics, loop_rest, make_glucose_lookup, observed_range,
    shape_description, slot_headline, slot_levers, verdict_class)
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
            met = curve_metrics(curve, pure.arange(0, window + 1, 10))
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
    if cre and not any(pure.is_nan(v) for v in cre):
        out["cre"] = f"{fmt_cr(cre[0])} – {fmt_cr(cre[1])}"
    ratio = stab["spread"].get("ratio")
    if ratio and not any(pure.is_nan(v) for v in ratio):
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
        low_d4 = not pure.is_nan(row["d4"]) and row["d4"] < g(D4_STRONG)
        out.append({
            "time": f"{row['time']:%d.%m %H:%M}", "label": _slot_state()[2][row["slot"]],
            "cho": f"{row['cho']:.0f}", "bolus": f"{row['bolus']:.1f}", "cr": fmt_cr(row["cr"]),
            "exc": "—" if pure.is_nan(row["exc"]) else f"{row['exc']:+.2f}", "cre": fmt_cr(row["cr_eff"]),
            "d4": fmt_delta(row["d4"]) if not pure.is_nan(row["d4"]) else "—",
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
    grid = pure.arange(0, window + 1, 10)
    recs, example, example_exc = [], None, 0.0
    stability = stability or {}
    selected = selected or {}
    for slot in _slot_state()[1]:
        curve = slot_median_curve(meals, slot, window, val_at)
        agg = aggregate_slot(by_slot.get(slot, []))
        if curve is None or agg is None or all(pure.is_nan(v) for v in curve):
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


def _daily_days(times, gluc, base, basal, events=None, tdd=None, progress=None):
    """Daily panels for the HTML report.

    One pass, not two: an SVG chart carries both themes in its own stylesheet,
    so there is no dark copy to render.
    """
    events = read_bolus_events(base) if events is None else events
    tdd = read_tdd(base) if tdd is None else tdd
    # The daily charts are one of the dominant report-generation costs. Report
    # progress once per completed day so the UI does not sit at one percentage
    # while a large multi-day report is being drawn.
    daily_progress = progress
    return daily_charts(times, gluc, events, basal, tdd,
                        progress=(lambda done, total: daily_progress("daily", done, total))
                                  if daily_progress else None)


def build_context(base, window, wlab, daily=False, lang="de",
                  assume_camaps=False, date_from=None, date_to=None, progress=None):
    """Read all data, analyse, and assemble the template context.

    ``progress`` is an optional callback receiving ``(stage, percent)``.
    It is deliberately advisory: progress reporting must never change the
    analysis result or make the core dependent on a particular UI.
    """
    def _progress(stage, percent):
        if progress is not None:
            progress(stage, percent)

    _progress("read", 5)
    ns = None
    # Name-based sources first: Glooko and Nightscout are recognised by file names
    # alone. Only when neither is there do the remaining readers open files to look
    # at their headers — so pointing at a real Glooko export reads nothing else.
    ns = None
    if is_glooko(base):
        pass
    elif is_nightscout(base):
        ns = read_nightscout(base)
    else:
        # Neither of the two name-based sources: only now is it worth opening
        # files to look at their headers.
        if is_libreview(base):
            ns = read_libreview(base)
        elif is_dexcom(base):
            ns = read_dexcom(base)
    if ns:
        times, gluc, name, sensor = ns["times"], ns["gluc"], ns["name"], ns["sensor"]
        meals, minors, pump = ns["meals"], ns["minors"], ns["pump"]
        basal = ns["basal"]
    else:
        times, gluc, name, sensor = read_cgm(base)
        meals, minors, pump = read_meals(base)
        basal = read_basal_timeline(base)
    source = ns["source"] if ns else "glooko"
    _progress("read", 25)
    # No basal in the export means no loop-aware part, whatever the source.
    lite = source in ("libreview", "dexcom") or (source == "nightscout"
                                                and not assume_camaps)
    events = ns["events"] if ns else None
    times, gluc, meals, minors, events = clip_by_days(
        times, gluc, meals, minors, events, date_from, date_to, window)
    val_at = make_glucose_lookup(times, gluc)
    # Plain datetimes: the gap check binary-searches them, which needs an
    # order and nothing else.
    cgm_stamps = list(times) if times is not None else None

    met = consensus_metrics(times, gluc)
    gri = gri_metrics(met)
    if basal is None and not lite:
        raise LoopCRError("No basal rates found.")
    # Without a basal trace the loop figures stay empty, but contamination, hypo
    # rescues and the return delta come from the glucose curve and are worked out
    # the same way - the assessment then rests on CHO/bolus and the delta alone.
    rows = analyze_meals(meals, minors, basal, window, val_at, cgm_times=cgm_stamps)
    _progress("meals", 50)
    by_slot = defaultdict(list)
    for row in rows:
        by_slot[row["slot"]].append(row)
    curve_cap, clean_note = _captions(meals, by_slot, window, val_at)
    # Also without a basal trace: the verdict rule falls back to the return delta,
    # and every derivation from the curve shape needs nothing but the glucose.
    selected = {slot: select_slot_rows(srows)[0] for slot, srows in by_slot.items()}
    stability = {slot: decision_stability(srows) for slot, srows in selected.items()}
    recs, cr_example = _recommendations_context(meals, by_slot, window, val_at,
                                                stability, selected)
    _progress("analysis", 70)
    device = " · ".join(p for p in (pump, sensor) if p) or _("device unknown")

    # Chart rendering dominates report generation for larger exports. Keep the
    # progress range reserved for the actual rendering work instead of jumping
    # to 90% before the charts start.
    _progress("charts", 71)
    chart_state = {"step": 0}

    def _daily_progress(_stage, done, total):   # stage: callback signature
        # One completed daily panel is one real unit of work.
        chart_state["step"] = done
        pct = 86 + int(11 * done / max(1, total))
        _progress(f"daily {done}/{total}", min(pct, 97))

    # Build the expensive charts in measured phases. The final report render is
    # deliberately kept separate so 100% only means the HTML is ready.
    gri_img = gri_grid_chart(gri)
    _progress("charts", 74)
    agp_img = agp_chart(times, gluc)
    _progress("charts", 77)
    slot_img = slot_curves_chart(meals, window, val_at)
    _progress("charts", 80)
    slot_norm_img = slot_norm_curves_chart(meals, window, val_at)
    _progress("charts", 86)
    daily_days = (_daily_days(times, gluc, base, basal,
                              events=events,
                              tdd=ns["tdd"] if ns else None,
                              progress=_daily_progress)
                  if daily else [])
    _progress("charts", 97)

    return {
        "source": source, "lite": lite,
        "tool": TOOL_NAME, "name": name, "span": f"{times[0]:%d.%m.%Y}–{times[-1]:%d.%m.%Y}",
        "generated": datetime.now().strftime("%d.%m.%Y, %H:%M"), "repo": REPO_URL,
        "version": tool_version(), "lang": lang,
        "days": f"{met['days']:.0f}", "device": device if lite else f"{device} · Auto Mode",
        "wear": f"{met['wear']:.0f}", "mean": fmt_glucose(met["mean"]), "gmi": f"{met['gmi']:.1f}",
        "cv": f"{met['cv']:.0f}", "tir": f"{met['tir']:.0f}", "titr": f"{met['titr']:.0f}",
        "gri": {**gri, "img": gri_img},
        "tir_bands": [{"label": lab, "val": f"{val:.1f}", "width": f"{min(val, 100):.1f}",
                       "color": col} for lab, val, col in _tir_bands(met)],
        "agp_img": agp_img,
        "slot_img": slot_img,
        "slot_norm_img": slot_norm_img,
        "selection": selection_effect(meals, by_slot, window, val_at),
        "daily_days": daily_days,
        "curve_cap": curve_cap,
        "slots": _slots_context(by_slot, meals, window, val_at, stability, selected),
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
    # No default: without a folder the tool used to search the working directory
    # recursively, which on a mistyped path meant walking a whole home directory
    # and opening every CSV on the way.
    parser.add_argument("export_dir",
                        help="unpacked export folder (numbered files are merged)")
    parser.add_argument("-o", "--out", default=None,
                        help="output HTML (default: ./<name>_loop-cr-review_<window>.html)")
    parser.add_argument("-w", "--window-hours", type=float, default=4.0,
                        help="postprandial window in hours (default 4.0; e.g. 3, 3.5, 4)")
    parser.add_argument("-t", "--template-dir", default=None,
                        help="folder containing report.html.j2 (default: ./templates next to this script)")
    parser.add_argument("-d", "--daily", action="store_true",
                        help="also output a daily overview (small day profiles per calendar day)")
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
                    daily=False, assume_camaps=False,
                    date_from=None, date_to=None,
                    slots=None, template_dir=None, progress=None):
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
                            assume_camaps=assume_camaps,
                            date_from=date_from, date_to=date_to, progress=progress)
        if progress is not None:
            progress("render", 98)
        html = render(context, tpl_dir)
        if progress is not None:
            progress("render", 99)
            progress("done", 100)
        return html, context


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
            daily=args.daily,
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
