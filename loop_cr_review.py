#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""AGP + Loop-aware CR-Report aus einem CamAPS/Glooko-Export.

Trennt Logik (dieses Modul) von Darstellung (report_template.html.j2). Liest CGM-,
Bolus- und Basaldaten, berechnet Konsens-Metriken sowie eine Loop-aware CR-Beurteilung
pro Tageszeit-Slot und rendert einen eigenstaendigen HTML-Report.
"""
import argparse
import base64
import csv
import io
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Font-Cache an festen Ort legen (im Onefile-Binary sonst pro Start neu gebaut) und die
# "building font cache"-Meldung stummschalten — vor dem matplotlib-Import setzen.
os.environ.setdefault("MPLCONFIGDIR", str(Path.home() / ".cache" / "loop-cr-review-mpl"))
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
import matplotlib  # noqa: E402  pylint: disable=wrong-import-position
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  pylint: disable=wrong-import-position

# --- Methoden-Parameter (datenunabhaengig) ---------------------------------
SLOTS = [("Fruehstueck", "Frühstück", 5, 10), ("Mittag", "Mittag", 11, 15),
         ("Abend", "Abend", 17, 22), ("Sonstige", "Sonstige", -1, -1)]
MAIN_SLOTS = ("Fruehstueck", "Mittag", "Abend")
SLOT_LABEL = {k: lab for k, lab, _, _ in SLOTS}
SLOT_COLOR = {"Fruehstueck": "#c0392b", "Mittag": "#e0913a", "Abend": "#3a9b46"}
MEAL_MIN_CHO = 20          # g, Untergrenze fuer "echte" Mahlzeit
MERGE_SEC = 45 * 60        # Boli innerhalb dieser Spanne zusammenfassen
FASTING_HOURS = (0, 1, 2, 3, 4)
LOOP_RATIO = 0.12          # |Loop-Mehrbasal / Bolus| ab hier auffaellig
D4_WEAK, D4_STRONG = 15, -30
D4_HIGH = 40               # Δ4h ab hier klar zu hoch (auch ohne Loop-Signal)
CR_DEV_LOW, CR_DEV_HIGH = 0.75, 1.33
PRE_BG_HIGH = 150
# Schwellen fuer die Kurvenform-Ableitungen
PEAK_EARLY = 75            # min: Peak vor dieser Zeit gilt als "frueh"
PEAK_RISE_HIGH = 55        # mg/dL Anstieg ueber Start: "hoher Peak"
NADIR_LOW = 85             # mg/dL: Tiefpunkt darunter = auffaellig
NADIR_LATE = 120           # min: Tief nach dieser Zeit = spaet (Insulin-Tail)
TIME_FMTS = ("%d.%m.%Y %H:%M",)
TOOL_NAME = "Loop-CR-Review"
REPO_URL = "https://github.com/peisenh/loop-cr-review"


# --- kleine Helfer ----------------------------------------------------------
def num(val):
    """Deutsches Zahlformat ('57,0') -> float; leer -> nan."""
    val = val.strip().strip('"')
    if val == "":
        return np.nan
    return float(val.replace(".", "").replace(",", ".")) if "," in val else float(val)


def parse_ts(val):
    """Zeitstempel aus dem Export nach datetime."""
    for fmt in TIME_FMTS:
        try:
            return datetime.strptime(val.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Unbekanntes Zeitformat: {val!r}")


def fig_to_b64(fig):
    """Matplotlib-Figur -> base64-PNG-String."""
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def fmt_cr(value):
    """Carb-Ratio als '1:x.x' oder '—' bei nan."""
    return f"1:{value:.1f}" if value and not np.isnan(value) else "—"


def slot_of(hour):
    """Tageszeit-Slot fuer eine Stunde."""
    for key, _lab, start, end in SLOTS:
        if start <= hour < end:
            return key
    return "Sonstige"


# --- Einlesen ---------------------------------------------------------------
def resource_dir():
    """Basisverzeichnis für mitgelieferte Dateien (Template).

    Als PyInstaller-Binary liegen die Daten in sys._MEIPASS, sonst neben diesem Modul.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", "."))
    return Path(__file__).resolve().parent


def numbered_csvs(directory, stem):
    """Alle nummerierten Export-Dateien <stem>_N.csv, numerisch sortiert.

    Glooko zerlegt grosse Exporte in cgm_data_1.csv, cgm_data_2.csv, ...
    """
    files = list(Path(directory).glob(f"{stem}_*.csv"))

    def order(path):
        match = re.search(rf"{re.escape(stem)}_(\d+)\.csv$", path.name)
        return int(match.group(1)) if match else 0

    return sorted(files, key=order)


def read_cgm(base):
    """-> (times[np.array], glucose[np.array], patient_name, sensor).

    Liest alle cgm_data_*.csv (Glooko splittet lange Zeitraeume auf mehrere Dateien).
    """
    times, gluc, sensor, name = [], [], "", "Patient"
    files = numbered_csvs(base, "cgm_data")
    if not files:
        raise FileNotFoundError(f"Keine cgm_data_*.csv in {base} gefunden")
    for idx, path in enumerate(files):
        with open(path, encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            meta = next(reader)
            next(reader)
            if idx == 0:
                match = re.search(r"Name\s*:\s*([^,]+)", ",".join(meta))
                if match:
                    name = match.group(1).strip()
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
    """-> (meals[list], pump). Mahlzeit = zusammengefasste Boli >= MEAL_MIN_CHO g mit Bolus."""
    raw, pump = [], ""
    for path in numbered_csvs(base / "Insulin data", "bolus_data"):
        with open(path, encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            next(reader)
            next(reader)
            for row in reader:
                if not pump and len(row) >= 9 and row[8].strip():
                    pump = row[8].strip()
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
    return meals, pump


def read_bolus_events(base):
    """Alle einzelnen Bolus-/KH-Einträge (unzusammengefasst) für die Tagesübersicht."""
    events = []
    for path in numbered_csvs(base / "Insulin data", "bolus_data"):
        with open(path, encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            next(reader)
            next(reader)
            for row in reader:
                cho, ins = num(row[3]), num(row[5])
                cho = 0.0 if np.isnan(cho) else cho
                ins = 0.0 if np.isnan(ins) else ins
                if cho > 0 or ins > 0:
                    events.append({"time": parse_ts(row[0]), "cho": cho, "bolus": ins})
    return events


def read_basal_timeline(base):
    """-> (rate[np.array U/h je Minute], t0, minutes, fasting_basal)."""
    segs = []
    for path in numbered_csvs(base / "Insulin data", "basal_data"):
        with open(path, encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            next(reader)
            next(reader)
            for row in reader:
                rate_val = num(row[4])
                if not np.isnan(rate_val):
                    dur = num(row[2])
                    segs.append((parse_ts(row[0]), int(dur) if not np.isnan(dur) else 5, rate_val))
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
    fasting = float(np.median([rate[i] for i in range(minutes)
                               if (t0 + timedelta(minutes=i)).hour in FASTING_HOURS]))
    return rate, t0, minutes, fasting


# --- Analyse ----------------------------------------------------------------
def consensus_metrics(times, gluc):
    """Konsens-Metriken (Battelino 2019) als dict."""
    mean, sd = float(gluc.mean()), float(gluc.std())
    days = (times[-1] - times[0]).total_seconds() / 86400
    step = np.median(np.diff([t.timestamp() for t in times])) / 60

    def pct(lo, hi):
        return 100 * float(np.mean((gluc >= lo) & (gluc <= hi)))

    return {
        "mean": mean, "cv": sd / mean * 100, "gmi": 3.31 + 0.02392 * mean, "days": days,
        "wear": 100 * len(gluc) / (days * 24 * 60 / step) if step else float("nan"),
        "tir": pct(70, 180), "titr": pct(70, 140),
        "tbr1": 100 * float(np.mean((gluc >= 54) & (gluc < 70))),
        "tbr2": 100 * float(np.mean(gluc < 54)),
        "tar1": 100 * float(np.mean((gluc > 180) & (gluc <= 250))),
        "tar2": 100 * float(np.mean(gluc > 250)),
    }


def make_glucose_lookup(times, gluc):
    """Closure: mediane Glukose ~minutes nach ref (+-tol)."""
    def val_at(ref, minutes, tol=12):
        lo, hi = ref + timedelta(minutes=minutes - tol), ref + timedelta(minutes=minutes + tol)
        mask = (times >= lo) & (times <= hi)
        return float(gluc[mask].mean()) if mask.any() else np.nan
    return val_at


def analyze_meals(meals, basal, window, val_at):
    """Pro Mahlzeit: Loop-Mehrbasal im Fenster, CR_eff, Return Δ, Kontamination.

    basal: (rate, t0, minutes, fasting) aus read_basal_timeline.
    """
    rate, t0, minutes, fasting = basal
    meal_times = [m["time"] for m in meals]
    rows = []
    for meal in meals:
        start = meal["time"]
        i0 = int((start - t0).total_seconds() // 60)
        if i0 < 0 or i0 + window >= minutes:
            continue
        contam = any(0 < (o - start).total_seconds() <= window * 60
                     for o in meal_times if o != start)
        excess = float(np.sum(rate[i0:i0 + window] - fasting) / 60.0)
        pre, post = val_at(start, 0), val_at(start, window)
        total = meal["bolus"] + excess
        rows.append({
            "slot": slot_of(start.hour), "time": start, "cho": meal["cho"],
            "bg": meal["bg"], "bolus": meal["bolus"], "pre": pre,
            "cr": meal["cho"] / meal["bolus"], "exc": excess,
            "cr_eff": meal["cho"] / total if total > 0 else np.nan,
            "d4": (post - pre) if not np.isnan(post) and not np.isnan(pre) else np.nan,
            "contam": contam,
        })
    return rows


def aggregate_slot(slot_rows):
    """Median-Aggregation eines Slots + Befund. -> dict oder None."""
    clean = [r for r in slot_rows if not r["contam"]]
    use = clean if len(clean) >= 3 else slot_rows
    if not use:
        return None

    def med(key):
        return float(np.nanmedian([r[key] for r in use if not np.isnan(r[key])]))

    exc, bol, d4 = med("exc"), med("bolus"), med("d4")
    ratio = exc / bol if bol else 0
    if ratio > LOOP_RATIO or d4 > D4_HIGH:
        flag, cls = "zu schwach → straffen", "weak"
    elif ratio < -LOOP_RATIO or d4 < D4_STRONG:
        flag, cls = "zu stark → lockern", "strong"
    else:
        flag, cls = "plausibel passend", "ok"
    return {"n": len(slot_rows), "clean": len(clean), "cho": med("cho"), "cr": med("cr"),
            "bol": bol, "exc": exc, "cre": med("cr_eff"), "d4": d4, "flag": flag, "cls": cls}


def slot_median_curve(meals, slot, window, val_at):
    """Median-Postprandialkurve (0..window) eines Slots oder None."""
    grid = np.arange(0, window + 1, 10)
    stacks = [[val_at(m["time"], int(g), 6) for g in grid]
              for m in meals if slot_of(m["time"].hour) == slot]
    return np.nanmedian(np.array(stacks), axis=0) if stacks else None


def shape_description(curve):
    """Kurze, datengetriebene Formbeschreibung einer Postprandialkurve."""
    if curve is None or np.all(np.isnan(curve)):
        return None
    start, end, low = np.nanmedian(curve[:2]), np.nanmedian(curve[-2:]), np.nanmin(curve)
    if low < 75:
        return "steigt an und fällt anschließend in tiefe Werte"
    if end - start > 25:
        return "klettert und kehrt nicht zum Ausgangswert zurück"
    if end - start < -25:
        return "fällt deutlich unter den Ausgangswert"
    return "kehrt nahe zum Ausgangswert zurück (ausgewogen)"


def curve_metrics(curve, grid):
    """Peak/Nadir/Start/Ende + 'steigt am Ende noch' aus einer Postprandialkurve."""
    pk, nd = int(np.nanargmax(curve)), int(np.nanargmin(curve))
    return {"start": float(np.nanmedian(curve[:2])), "end": float(np.nanmedian(curve[-2:])),
            "peak": float(curve[pk]), "peak_t": int(grid[pk]),
            "nadir": float(curve[nd]), "nadir_t": int(grid[nd]),
            "rising_end": float(curve[-1]) - float(curve[-3]) > 5}


def slot_levers(agg, met, window):
    """Kandidaten-Stellschrauben (Tag, CSS-Klasse, Text) aus Befund + Kurvenform."""
    levers = []
    if agg["cls"] != "ok" and met["peak_t"] <= PEAK_EARLY and met["peak"] - met["start"] >= PEAK_RISE_HIGH:
        levers.append(("SEA", "sea", "früher hoher Peak → längeren Spritz-Ess-Abstand prüfen "
                                     "(kappt die Spitze ohne mehr Dosis)"))
    if agg["cls"] == "weak":
        levers.append(("Dosis", "cr", f"unterdeckt → CR straffen, grobe Richtung CR_eff {fmt_cr(agg['cre'])}"))
    elif agg["cls"] == "strong":
        levers.append(("Dosis", "cr", "überdeckt/Abfall → Dosis dieser Mahlzeit eher reduzieren; "
                                      "SEA und Dosis zusammen betrachten"))
    late_rise = met["peak_t"] >= window * 0.66 and met["end"] - met["start"] > 20
    if late_rise and agg["cls"] != "ok":
        levers.append(("Fett/Protein", "fp", "monotoner Spätanstieg (kein Umkehrpunkt) → Fett/Protein "
                                             "prüfen; ggf. verzögerter/Dual-Bolus statt nur straffen"))
    elif late_rise:
        levers.append(("Beobachten", "obs", "leichter später Wiederanstieg → ggf. Fett/Protein oder "
                                            "Basalrate in diesem Zeitfenster, nur im Auge behalten"))
    if met["nadir"] < NADIR_LOW and met["nadir_t"] >= NADIR_LATE:
        levers.append(("Achtung", "obs", f"Tief ~{met['nadir']:.0f} mg/dL gegen {met['nadir_t']} min "
                                         "→ Hypo-Fenster zuerst absichern"))
    if agg["cls"] == "ok" and not any(t == "Dosis" for t, _, _ in levers):
        levers.append(("Referenz", "obs", "Dosis & Timing passen — so belassen; "
                                          "dient als Vergleich für die anderen Slots"))
    if not levers:
        levers.append(("—", "obs", "keine auffällige Form"))
    return levers


def slot_headline(agg, met):
    """Befund-bewusste Kurzbeschreibung der Slot-Form (konsistent zum Befund)."""
    rise_end = met["end"] - met["start"]
    early_high = met["peak_t"] <= PEAK_EARLY and met["peak"] - met["start"] >= PEAK_RISE_HIGH
    if agg["cls"] == "strong":
        return ("hoher Peak, danach Abfall unter die Ausgangslage" if met["nadir"] < NADIR_LOW
                else "fällt unter den Ausgangswert")
    if agg["cls"] == "weak":
        return "klettert und kehrt nicht zum Ausgangswert zurück"
    if rise_end > 20:
        return "leichter Spätanstieg, netto aber ausgewogen"
    if early_high:
        return "früher Peak, kehrt anschließend sauber zurück"
    return "kehrt nahe zum Ausgangswert zurück (ausgewogen)"


def build_cr_note(rows, by_slot):
    """Datengetriebener Hinweis zu auffaelligen abgeleiteten CR-Werten (HTML-Snippet)."""
    all_cr = [r["cr"] for r in rows if not np.isnan(r["cr"])]
    med_cr = float(np.median(all_cr)) if all_cr else float("nan")
    dev = []
    for slot in MAIN_SLOTS:
        srows = by_slot.get(slot, [])
        if len(srows) < 3:
            continue
        scr = float(np.nanmedian([r["cr"] for r in srows]))
        pres = [r["pre"] for r in srows if not np.isnan(r["pre"])]
        spre = float(np.nanmedian(pres)) if pres else float("nan")
        if not np.isnan(scr) and (scr < CR_DEV_LOW * med_cr or scr > CR_DEV_HIGH * med_cr):
            dev.append((slot, scr, spre))
    if not dev:
        return f"• Abgeleitete CR = CHO/Bolus; kein Slot weicht auffällig vom Median (1:{med_cr:.1f}) ab.<br>"
    parts = []
    for slot, scr, spre in dev:
        direction = "straffer" if scr < med_cr else "lockerer"
        if not np.isnan(spre) and spre > PRE_BG_HIGH:
            hint = ("erhöhter prä-BZ → vom Rechner beigemischte Korrektur wahrscheinlich, "
                    "abgeleitete CR unterschätzt die programmierte Ratio")
        else:
            hint = "prä-BZ nicht deutlich erhöht → eher genuin andere programmierte Ratio als reine Korrektur"
        parts.append(f"{SLOT_LABEL[slot]}: abgeleitete CR 1:{scr:.1f} ({direction} als "
                     f"Median 1:{med_cr:.1f}), prä-BZ ~{spre:.0f} mg/dL – {hint}")
    return ("• Abgeleitete CR = CHO/Bolus (enthält ggf. beigemischte Korrekturen). Auffällige "
            "Abweichungen: " + "; ".join(parts) + ". Klärung (programmierte Ratio vs. "
            "Korrekturfaktor vs. Timing) durch das Team.<br>")


# --- Charts -----------------------------------------------------------------
def agp_chart(times, gluc):
    """AGP-Perzentilgrafik als base64-PNG."""
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
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.axhspan(70, 180, color="#dff0df")
    ax.axhline(70, color="#5a5", lw=.7)
    ax.axhline(180, color="#5a5", lw=.7)
    ax.fill_between(xs, perc[5], perc[95], color="#bcd4ff", alpha=.6, label="5–95 %")
    ax.fill_between(xs, perc[25], perc[75], color="#5b8def", alpha=.55, label="25–75 %")
    ax.plot(xs, perc[50], color="#0b2e6b", lw=2, label="Median")
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_ylim(40, 300)
    ax.set_xlabel("Uhrzeit")
    ax.set_ylabel("mg/dL")
    ax.legend(fontsize=8, ncol=3, loc="upper right")
    ax.grid(alpha=.25)
    return fig_to_b64(fig)


def slot_curves_chart(meals, window, val_at):
    """Mediane Postprandialkurven je Slot als base64-PNG."""
    grid = np.arange(0, window + 1, 10)
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.axhspan(70, 180, color="#dff0df")
    for slot in MAIN_SLOTS:
        curve = slot_median_curve(meals, slot, window, val_at)
        if curve is not None:
            n = sum(1 for m in meals if slot_of(m["time"].hour) == slot)
            ax.plot(grid, curve, color=SLOT_COLOR[slot], lw=2,
                    label=f"{SLOT_LABEL[slot]} (n={n})")
    ax.set_xlim(0, window)
    ax.set_ylim(60, 240)
    ax.set_xlabel("Minuten ab Mahlzeit")
    ax.set_ylabel("mg/dL")
    ax.legend(fontsize=8)
    ax.grid(alpha=.25)
    return fig_to_b64(fig)


# --- Context / Rendering ----------------------------------------------------
WEEKDAYS_DE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
DAILY_BOLUS_Y, DAILY_CARB_Y, DAILY_ROW, DAILY_MIN_GAP = 452, 388, 18, 0.9


def _draw_labels(axg, items, base_y, color, bold=False):
    """Labels (hour, text) einer Sorte platzieren; nur bei echter Nähe in Zeilen versetzen."""
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


def _draw_day_events(axg, events):
    """Alle Bolus-Einträge (dunkelblau/fett, oben) und KH-Einträge (rot, darunter) eines Tages."""
    def hour(event):
        return event["time"].hour + event["time"].minute / 60
    _draw_labels(axg, [(hour(e), f"{e['bolus']:.1f} E") for e in events if e["bolus"] > 0],
                 DAILY_BOLUS_Y, "#0b2e6b", bold=True)
    _draw_labels(axg, [(hour(e), f"{e['cho']:.0f} g") for e in events if e["cho"] > 0],
                 DAILY_CARB_Y, "#c0392b")


def daily_charts(times, gluc, events, basal):
    """Ein seitenbreites Panel je Tag (CGM + alle Bolus-/KH-Einträge + Basal), neueste zuerst."""
    rate, t0, minutes = basal[:3]
    gmax = float(np.nanmax(rate)) or 1.0           # globale Basal-Skala für alle Tage gleich
    cgm_by, ev_by = defaultdict(list), defaultdict(list)
    for time, value in zip(times, gluc):
        cgm_by[time.date()].append((time.hour + time.minute / 60, value))
    for event in events:
        ev_by[event["time"].date()].append(event)
    out = []
    for day in sorted(cgm_by, reverse=True):
        fig, axg = plt.subplots(figsize=(11, 2.5))
        axg.axhspan(70, 180, color="#dff0df")
        axg.plot([x for x, _ in cgm_by[day]], [y for _, y in cgm_by[day]], color="#0b2e6b", lw=1.0)
        axg.set_xlim(0, 24)
        axg.set_ylim(40, 470)
        axg.set_xticks(range(0, 25, 3))
        axg.set_yticks([70, 180, 300])
        axg.tick_params(labelsize=7)
        axg.grid(axis="x", alpha=.15)
        axg.set_title(f"{WEEKDAYS_DE[day.weekday()]}, {day:%d.%m.%Y}",
                      fontsize=8, loc="left", color="#1a2233")
        i0 = int((datetime(day.year, day.month, day.day) - t0).total_seconds() // 60)
        bxx = [mnt / 60 for mnt in range(0, 24 * 60, 5)]
        byy = [rate[i0 + mnt] if 0 <= i0 + mnt < minutes else 0.0 for mnt in range(0, 24 * 60, 5)]
        ax2 = axg.twinx()
        ax2.fill_between(bxx, byy, step="pre", color="#5b8def", alpha=.35, lw=0)
        ax2.set_ylim(0, gmax * 2.2)                 # unteres ~45 %, für alle Tage gleiche Skala
        ax2.set_xlim(0, 24)
        ax2.set_yticks([0, round(gmax, 1)])
        ax2.set_ylabel("U/h", fontsize=6, color="#3a63a8")
        ax2.tick_params(labelsize=6, colors="#3a63a8")
        _draw_day_events(axg, ev_by.get(day, []))
        out.append({"img": fig_to_b64(fig)})
    return out


def _slots_context(by_slot):
    out = []
    for slot in ("Fruehstueck", "Mittag", "Abend", "Sonstige"):
        agg = aggregate_slot(by_slot.get(slot, []))
        if not agg:
            continue
        out.append({
            "label": SLOT_LABEL[slot], "n": agg["n"], "clean": agg["clean"],
            "cho": f"{agg['cho']:.0f}", "cr": fmt_cr(agg["cr"]), "bol": f"{agg['bol']:.1f}",
            "exc": f"{agg['exc']:+.2f}", "cre": fmt_cr(agg["cre"]), "d4": f"{agg['d4']:+.0f}",
            "flag": agg["flag"], "cls": agg["cls"],
        })
    return out


def _meals_context(rows):
    out = []
    for row in sorted(rows, key=lambda r: r["time"]):
        cls = ""
        if not np.isnan(row["d4"]):
            weak = (row["exc"] / row["bolus"] if row["bolus"] else 0) > LOOP_RATIO and row["d4"] > D4_WEAK
            cls = "strong" if row["d4"] < D4_STRONG else "weak" if weak else ""
        out.append({
            "time": f"{row['time']:%d.%m %H:%M}", "label": SLOT_LABEL[row["slot"]],
            "cho": f"{row['cho']:.0f}", "bolus": f"{row['bolus']:.1f}", "cr": fmt_cr(row["cr"]),
            "exc": f"{row['exc']:+.2f}", "cre": fmt_cr(row["cr_eff"]),
            "d4": f"{row['d4']:+.0f}" if not np.isnan(row["d4"]) else "—",
            "contam": row["contam"], "cls": cls,
        })
    return out


def _captions(meals, by_slot, window, val_at):
    """(curve_cap, clean_note) datengetrieben aus den Slot-Kurven/Kontaminationen."""
    caps = []
    for slot in MAIN_SLOTS:
        desc = shape_description(slot_median_curve(meals, slot, window, val_at))
        if desc:
            caps.append(f"{SLOT_LABEL[slot]} {desc}")
    curve_cap = "; ".join(caps) + "." if caps else \
        "Zu wenige Mahlzeiten je Slot für eine belastbare Formbeschreibung."
    low_clean = [SLOT_LABEL[s] for s in MAIN_SLOTS if by_slot.get(s)
                 and sum(not r["contam"] for r in by_slot[s]) / len(by_slot[s]) < 0.5]
    clean_note = f" (v.a. {', '.join(low_clean)})" if low_clean else ""
    return curve_cap, clean_note


def _recommendations_context(meals, by_slot, window, val_at):
    """Pro Slot: Kurven-Metriken + abgeleitete Stellschrauben; plus CR_eff-Beispiel."""
    grid = np.arange(0, window + 1, 10)
    recs, example, example_exc = [], None, 0.0
    for slot in MAIN_SLOTS:
        curve = slot_median_curve(meals, slot, window, val_at)
        agg = aggregate_slot(by_slot.get(slot, []))
        if curve is None or agg is None or np.all(np.isnan(curve)):
            continue
        met = curve_metrics(curve, grid)
        recs.append({
            "label": SLOT_LABEL[slot], "cls": agg["cls"], "headline": slot_headline(agg, met),
            "peak": f"{met['peak']:.0f}", "peak_t": met["peak_t"],
            "nadir": f"{met['nadir']:.0f}", "nadir_t": met["nadir_t"],
            "d4": f"{agg['d4']:+.0f}", "loop": f"{agg['exc']:+.2f}",
            "cr": fmt_cr(agg["cr"]), "cre": fmt_cr(agg["cre"]),
            "levers": [{"tag": t, "cls": c, "text": x} for t, c, x in slot_levers(agg, met, window)],
        })
        if agg["cls"] == "weak" and (example is None or agg["exc"] > example_exc):
            example, example_exc = ({"label": SLOT_LABEL[slot], "cho": f"{agg['cho']:.0f}",
                                     "bol": f"{agg['bol']:.1f}", "loop": f"{agg['exc']:.1f}",
                                     "cre": fmt_cr(agg["cre"]), "d4": f"{agg['d4']:+.0f}",
                                     "underdosed": agg["d4"] > D4_WEAK}, agg["exc"])
    return recs, example


def build_context(base, window, wlab, daily=False):
    """Alle Daten lesen, analysieren und den Template-Context zusammenstellen."""
    times, gluc, name, sensor = read_cgm(base)
    meals, pump = read_meals(base)
    basal = read_basal_timeline(base)
    val_at = make_glucose_lookup(times, gluc)

    met = consensus_metrics(times, gluc)
    rows = analyze_meals(meals, basal, window, val_at)
    by_slot = defaultdict(list)
    for row in rows:
        by_slot[row["slot"]].append(row)

    curve_cap, clean_note = _captions(meals, by_slot, window, val_at)
    recs, cr_example = _recommendations_context(meals, by_slot, window, val_at)
    device = " · ".join(p for p in (pump, sensor) if p) or "Gerät unbekannt"
    tir_bands = [("Very High &gt;250", met["tar2"], "#b23b3b"),
                 ("High 181–250", met["tar1"], "#e0913a"),
                 ("Target 70–180", met["tir"], "#3a9b46"),
                 ("Low 54–69", met["tbr1"], "#c0392b"),
                 ("Very Low &lt;54", met["tbr2"], "#7d1f1f")]

    return {
        "tool": TOOL_NAME, "name": name, "span": f"{times[0]:%d.%m.%Y}–{times[-1]:%d.%m.%Y}",
        "generated": datetime.now().strftime("%d.%m.%Y, %H:%M"), "repo": REPO_URL,
        "days": f"{met['days']:.0f}", "device": f"{device} · Auto Mode",
        "wear": f"{met['wear']:.0f}", "mean": f"{met['mean']:.0f}", "gmi": f"{met['gmi']:.1f}",
        "cv": f"{met['cv']:.0f}", "tir": f"{met['tir']:.0f}", "titr": f"{met['titr']:.0f}",
        "tir_bands": [{"label": lab, "val": f"{val:.1f}", "width": f"{min(val, 100):.1f}",
                       "color": col} for lab, val, col in tir_bands],
        "agp_img": agp_chart(times, gluc), "slot_img": slot_curves_chart(meals, window, val_at),
        "daily_days": daily_charts(times, gluc, read_bolus_events(base), basal) if daily else [],
        "curve_cap": curve_cap, "slots": _slots_context(by_slot), "meals": _meals_context(rows),
        "cr_note": build_cr_note(rows, by_slot), "clean_note": clean_note,
        "recs": recs, "cr_example": cr_example,
        "fb": f"{basal[3]:.2f}", "wlab": wlab,
    }


def render(context, template_dir):
    """Template mit dem Context rendern und HTML zurueckgeben."""
    env = Environment(loader=FileSystemLoader(str(template_dir)),
                      autoescape=select_autoescape(["html", "j2"]))
    return env.get_template("report.html.j2").render(**context)


def parse_args():
    """CLI-Argumente parsen."""
    parser = argparse.ArgumentParser(description="AGP + Loop-aware CR-Report aus CamAPS/Glooko-Export")
    parser.add_argument("export_dir", nargs="?", default=".",
                        help="entpackter Export-Ordner (nummerierte Dateien werden zusammengeführt)")
    parser.add_argument("-o", "--out", default=None,
                        help="Ausgabe-HTML (Default: ./<name>_loop-cr-review_<fenster>.html)")
    parser.add_argument("-w", "--window-hours", type=float, default=4.0,
                        help="Postprandiales Fenster in Stunden (Default 4.0; z.B. 3, 3.5, 4)")
    parser.add_argument("-t", "--template-dir", default=None,
                        help="Ordner mit report.html.j2 (Default: ./templates neben diesem Script)")
    parser.add_argument("-d", "--daily", action="store_true",
                        help="Tagesübersicht (kleine Tagesprofile je Kalendertag) mit ausgeben")
    return parser.parse_args()


def main():
    """Report bauen und schreiben."""
    for stream in (sys.stdout, sys.stderr):        # Windows-Konsole (cp1252) sonst Crash bei '→'
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = parse_args()
    window = int(round(args.window_hours * 60))
    wlab = (f"{int(args.window_hours)}h" if float(args.window_hours).is_integer()
            else f"{args.window_hours:g}h")
    template_dir = (Path(args.template_dir) if args.template_dir
                    else resource_dir() / "templates")

    context = build_context(Path(args.export_dir), window, wlab, args.daily)
    html = render(context, template_dir)

    slug = re.sub(r"[^a-z0-9]+", "_", context["name"].lower()).strip("_") or "patient"
    out = Path(args.out) if args.out else Path(f"{slug}_loop-cr-review_{wlab}.html")
    out.write_text(html, encoding="utf-8")
    print(f"geschrieben: {out} | {len(html)} bytes")
    print(" | ".join(f"{s['label']}={s['flag']}" for s in context["slots"]
                     if s["label"] in ("Frühstück", "Mittag", "Abend")))


if __name__ == "__main__":
    main()
