# SPDX-FileCopyrightText: 2026 Peter Eisenhauer
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Multi-day closed-loop run written out as a Glooko-style export.

Why bother writing CSVs instead of handing arrays to the analysis: the export
is the only way to exercise the *real* readers, the fasting-basal reference and
the slot logic. Anything short of that would validate a second, simulation-only
analysis path.

Deliberately imports nothing from the analysis code — the simulation must stay
independent of the tool it is used to test.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from simglucose.patient.t1dpatient import Action, T1DPatient

from sim.controller import CGMOnlyPID, Gains, MID
from sim.noise import cgm_noise
from sim.physiology import MEAL_EAT_RATE_G_PER_MIN, basal_u_per_hour

PUMP = "CamAPS mylife YpsoPump"
SENSOR = "CamAPS FreeStyle Libre 3"
CGM_STEP_MIN = 5          # real Glooko grid; the loop itself runs per minute
BASAL_STEP_MIN = 10       # one basal segment per 10 min, as in real exports
# minute of day -> (grams, label); nights stay meal-free so the fasting basal
# reference the tool relies on can actually be measured.
DEFAULT_MEALS = ((7 * 60 + 30, 45.0), (12 * 60 + 30, 60.0), (18 * 60 + 30, 50.0))


@dataclass(frozen=True)
class DayRun:
    """Everything the export needs from one simulated run."""
    start: datetime
    cgm: list[tuple[datetime, float]]
    basal: list[tuple[datetime, float]]          # (start, U/h) per segment
    boluses: list[tuple[datetime, float, float]]  # (time, grams, units)


def run_days(patient_name: str = "adult#001", days: int = 14,
             cr_set: float = 10.0, gains: Gains = MID,
             meals: tuple = DEFAULT_MEALS,
             start: datetime | None = None,
             noise_sigma: float = 0.0,
             rng=None) -> DayRun:
    """Simulate ``days`` days of closed loop with three announced meals a day.

    ``noise_sigma`` is CGM noise in mg/dl, seen by the PID and written to
    the export. Pass a seeded ``random.Random`` so replicates differ.
    """
    patient = T1DPatient.withName(patient_name)
    profile_u_h = basal_u_per_hour(patient)
    target = float(patient.observation.Gsub)
    pid = CGMOnlyPID(profile_u_h, target, gains)
    start = start or datetime(2026, 5, 1, 0, 0)

    cgm: list[tuple[datetime, float]] = []
    basal: list[tuple[datetime, float]] = []
    boluses: list[tuple[datetime, float, float]] = []
    seg_sum, seg_n, seg_start = 0.0, 0, start
    remaining_cho = 0.0

    for minute in range(days * 24 * 60):
        now = start + timedelta(minutes=minute)
        glucose = cgm_noise(float(patient.observation.Gsub), rng, noise_sigma)
        basal_uh = pid.policy(glucose, sample_min=1.0)

        cho = 0.0
        insulin = basal_uh / 60.0
        for meal_min, grams in meals:
            if minute % (24 * 60) == meal_min:
                remaining_cho = grams
                bolus = grams / cr_set
                insulin += bolus
                boluses.append((now, grams, bolus))
        if remaining_cho > 0:
            cho = min(MEAL_EAT_RATE_G_PER_MIN, remaining_cho)
            remaining_cho -= cho

        patient.step(Action(CHO=cho, insulin=insulin))

        if minute % CGM_STEP_MIN == 0:
            cgm.append((now, glucose))
        seg_sum += basal_uh
        seg_n += 1
        if seg_n == BASAL_STEP_MIN:
            basal.append((seg_start, seg_sum / seg_n))
            seg_sum, seg_n, seg_start = 0.0, 0, now + timedelta(minutes=1)

    return DayRun(start=start, cgm=cgm, basal=basal, boluses=boluses)


def _fmt(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _write(path: Path, header: list[str], rows: list[list[str]],
           name: str, span: str) -> None:
    """Write one CSV the way Glooko does: BOM, two header lines, CRLF."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerow([f"Name:{name}", f"Datumsbereich:{span}"])
        writer.writerow(header)
        writer.writerows(rows)


def write_export(run: DayRun, out_dir: Path, name: str = "Sim Patient") -> Path:
    """Write a Glooko-style export the real readers can consume. -> out_dir."""
    out_dir = Path(out_dir)
    stamp = "%d.%m.%Y %H:%M"
    span = f"{run.cgm[0][0]:%d.%m.%Y} - {run.cgm[-1][0]:%d.%m.%Y}"

    _write(out_dir / "cgm_data_1.csv",
           ["Zeitstempel", "CGM-Glukosewert (mg/dl)", "Seriennummer"],
           [[f"{t:{stamp}}", _fmt(v, 1), SENSOR] for t, v in run.cgm],
           name, span)

    ins = out_dir / "Insulin data"
    _write(ins / "bolus_data_1.csv",
           ["Zeitstempel", "Insulin-Typ", "Blutzuckereingabe (mg/dl)",
            "Kohlenhydrataufnahme (g)", "Kohlenhydratverhältnis",
            "Abgegebenes Insulin (E)", "Anfängliche Abgabe", "Verzögert",
            "Seriennummer"],
           [[f"{t:{stamp}}", "Normal", _fmt(0.0, 1), _fmt(g, 1), "",
             _fmt(u, 2), "", "", PUMP] for t, g, u in run.boluses],
           name, span)

    _write(ins / "basal_data_1.csv",
           ["Zeitstempel", "Insulin-Typ", "Dauer (Minuten)", "Prozentsatz (%)",
            "Rate", "Abgegebenes Insulin (E)", "Seriennummer"],
           [[f"{t:{stamp}}", "Eingeplant", str(BASAL_STEP_MIN), "",
             _fmt(rate, 2), "", PUMP] for t, rate in run.basal],
           name, span)

    # Daily totals, stamped at 23:00 like the real file.
    by_day: dict = {}
    for t, _g, u in run.boluses:
        by_day.setdefault(t.date(), [0.0, 0.0])[0] += u
    for t, rate in run.basal:
        by_day.setdefault(t.date(), [0.0, 0.0])[1] += rate * BASAL_STEP_MIN / 60.0
    _write(ins / "insulin_data_1.csv",
           ["Zeitstempel", "Bolus gesamt (U)", "Insulin gesamt (U)",
            "Basal gesamt (U)", "Seriennummer"],
           [[f"{datetime.combine(day, datetime.min.time()).replace(hour=23):{stamp}}",
             _fmt(bolus), _fmt(bolus + basal), _fmt(basal), PUMP]
            for day, (bolus, basal) in sorted(by_day.items())],
           name, span)
    return out_dir
