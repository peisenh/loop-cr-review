#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Peter Eisenhauer
# SPDX-License-Identifier: AGPL-3.0-or-later
"""How large a carb-ratio error does the method actually notice, and when?

Complements ``validate_bootstrap.py``: that one asks whether the resampling
behaves as advertised, this one asks what the verdict rule can *see*. Slots are
generated from a known carb-ratio error and run through the real rule, then:

* **detection rate** — how often the correct direction (too weak / too strong)
  comes out, by number of days and size of the error;
* **false alarms** — how often a correctly set slot is nevertheless flagged;
* **robustness** — what outliers, CGM gaps and bolus noise do to both;
* **threshold sensitivity** — what happens if LOOP_RATIO is moved by ±10 %.

The generator uses the tool's own premise (loop extra basal covers part of the
meal's shortfall). That makes these numbers an **upper bound**: they describe
detection under ideal conditions, not on real exports where adaptation, fat and
protein, corrections and exercise blur the same signal. Deliberately not varied
here: the postprandial window, because these rows are synthesised post-window
and varying it would only re-scale the generator, not test the pipeline.

Usage:
    python3 tools/validate_sensitivity.py
    python3 tools/validate_sensitivity.py --reps 800 --markdown
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import loop_cr_review as core   # noqa: E402  pylint: disable=wrong-import-position

CHO = 60.0          # g per meal
CR_SET = 10.0       # g/U programmed
ISF = 40.0          # mg/dL per U, to turn uncovered insulin into a 4 h delta
LOOP_SHARE = 0.7    # fraction of the shortfall the loop compensates as basal
# Noise calibrated against real exports: day-to-day sd of the loop extra is
# roughly 1.1-3.7 U per slot and of the 4 h delta 27-78 mg/dL.
DAY_COUNTS = (5, 7, 10, 14, 21)
ERRORS = (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30)


def make_slot(n_days, error, rng, noise=1.2, disturb=None):
    """Rows for a slot whose true need deviates from the set CR by ``error``.

    ``error`` > 0 means the set ratio is too weak (too little insulin per gram).
    The shortfall is split: ``LOOP_SHARE`` shows up as loop extra basal, the rest
    as a raised 4 h delta — the signal the verdict rule is built on.
    """
    disturb = disturb or {}
    outliers = disturb.get("outliers", 0.0)
    gaps = disturb.get("gaps", 0.0)
    bolus_noise = disturb.get("bolus_noise", 0.0)
    bolus = CHO / CR_SET
    true_cr = CR_SET * (1.0 - error) if error else CR_SET
    shortfall = CHO / true_cr - bolus              # units the meal really needed
    rows, day0 = [], datetime(2026, 5, 1, 8, 0)
    for day in range(n_days):
        scale = 3.0 if rng.random() < outliers else 1.0
        given = bolus * (1 + rng.normal(0, bolus_noise)) if bolus_noise else bolus
        exc = LOOP_SHARE * shortfall + rng.normal(0, noise * scale)
        d4 = (1 - LOOP_SHARE) * shortfall * ISF + rng.normal(0, 40 * scale)
        rows.append({
            "time": day0 + timedelta(days=day),
            "exc": float(exc), "bolus": float(given),
            "d4": float("nan") if rng.random() < gaps else float(d4),
            "cho": CHO, "cr": CR_SET, "cr_eff": CHO / max(given + exc, 0.1),
            "contam": False, "cgm_gap": False, "hypo_rescue": False,
            "pre": 120.0, "bg": 120.0,
        })
    return rows


def _verdict(rows):
    """The real rule on median values — same path the report takes."""
    def med(key):
        vals = [r[key] for r in rows if not np.isnan(r[key])]
        return float(np.median(vals)) if vals else float("nan")
    return core.verdict_class(med("exc"), med("bolus"), med("d4"))


def detection_grid(reps, rng, disturb=None):
    """Detection rate per (days, error). At error 0 this is the false-alarm rate."""
    grid = {}
    for error in ERRORS:
        for n_days in DAY_COUNTS:
            hits = 0
            for _ in range(reps):
                cls = _verdict(make_slot(n_days, error, rng, disturb=disturb))
                hits += (cls == "ok") if error == 0 else (cls == "weak")
            grid[(error, n_days)] = 100.0 * hits / reps
    return grid


def perturbation_table(reps, rng):
    """Detection of a 20 % error at 10 days under different disturbances."""
    cases = (("clean", None),
             ("20 % outlier days", {"outliers": 0.2}),
             ("20 % CGM gaps", {"gaps": 0.2}),
             ("10 % bolus noise", {"bolus_noise": 0.1}),
             ("all three", {"outliers": 0.2, "gaps": 0.2, "bolus_noise": 0.1}))
    out = []
    for label, disturb in cases:
        det = sum(_verdict(make_slot(10, 0.20, rng, disturb=disturb)) == "weak"
                  for _ in range(reps))
        false = sum(_verdict(make_slot(10, 0.0, rng, disturb=disturb)) != "ok"
                    for _ in range(reps))
        out.append((label, 100.0 * det / reps, 100.0 * false / reps))
    return out


def threshold_table(reps, rng):
    """Does moving LOOP_RATIO by ±10 % change the picture?"""
    base = core.LOOP_RATIO
    out = []
    for label, factor in (("-10 %", 0.9), ("as shipped", 1.0), ("+10 %", 1.1)):
        core.LOOP_RATIO = base * factor
        det = sum(_verdict(make_slot(10, 0.20, rng)) == "weak" for _ in range(reps))
        false = sum(_verdict(make_slot(10, 0.0, rng)) != "ok" for _ in range(reps))
        out.append((label, round(core.LOOP_RATIO, 4),
                    100.0 * det / reps, 100.0 * false / reps))
    core.LOOP_RATIO = base
    return out


def _print_plain(grid, pert, thr):
    print("Detection rate by days and true CR error")
    print("  (error 0 % column = correctly reported as 'ok')")
    header = " error |" + "".join(f"{d:>7}d" for d in DAY_COUNTS)
    print(header)
    for error in ERRORS:
        row = "".join(f"{grid[(error, d)]:6.0f}%" + " " for d in DAY_COUNTS)
        print(f" {error * 100:4.0f}% | {row}")
    print("\nDetection of a 20 % error at 10 days under disturbance")
    print(" case                 | detected | false alarm (correct slot)")
    for label, det, false in pert:
        print(f" {label:<20} | {det:7.0f}% | {false:24.0f}%")
    print("\nThreshold sensitivity (LOOP_RATIO, 20 % error, 10 days)")
    print(" setting     | value  | detected | false alarm")
    for label, value, det, false in thr:
        print(f" {label:<11} | {value:6.3f} | {det:7.0f}% | {false:10.0f}%")


def _print_markdown(grid, pert, thr):
    print("| true CR error | " + " | ".join(f"{d} days" for d in DAY_COUNTS) + " |")
    print("|---:|" + "---:|" * len(DAY_COUNTS))
    for error in ERRORS:
        cells = " | ".join(f"{grid[(error, d)]:.0f} %" for d in DAY_COUNTS)
        label = "0 % (correct)" if error == 0 else f"{error * 100:.0f} %"
        print(f"| {label} | {cells} |")
    print("\n| disturbance | detected | false alarm |")
    print("|:---|---:|---:|")
    for label, det, false in pert:
        print(f"| {label} | {det:.0f} % | {false:.0f} % |")
    print("\n| threshold | value | detected | false alarm |")
    print("|:---|---:|---:|---:|")
    for label, value, det, false in thr:
        print(f"| {label} | {value:.3f} | {det:.0f} % | {false:.0f} % |")


def main():
    """Run the sensitivity analysis and print the tables."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    parser.add_argument("--reps", type=int, default=400)
    parser.add_argument("--seed", type=int, default=20260819)
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    grid = detection_grid(args.reps, rng)
    pert = perturbation_table(args.reps, rng)
    thr = threshold_table(args.reps, rng)
    if args.markdown:
        _print_markdown(grid, pert, thr)
    else:
        _print_plain(grid, pert, thr)


if __name__ == "__main__":
    main()
