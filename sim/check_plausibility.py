"""Spec §10 / §13.1 — physiology only, no controller.

1. Meal, no bolus → glucose rises.
2. Meal + bolus (provisional CR) → peak, then closer to baseline at 4 h
   than the no-bolus run.
3. Night, no meal → stays flat.
"""

from __future__ import annotations

import statistics
import sys

from sim.physiology import at, run_open_loop

PATIENT = "adult#001"
MEAL_G = 50.0
MEAL_AT = 60
WINDOW = 240
PROVISIONAL_CR = 10.0  # g/U — not CR_true; only to show a bolus has an effect


def check_meal_rises() -> None:
    tr = run_open_loop(
        PATIENT, minutes=MEAL_AT + WINDOW + 1,
        meal_at=MEAL_AT, meal_g=MEAL_G,
    )
    start, late = at(tr, MEAL_AT), at(tr, MEAL_AT + 180)
    if late - start < 40:
        raise SystemExit(
            f"meal without bolus should raise glucose: {start:.1f} → {late:.1f}"
        )
    print(f"ok meal rises  {start:.1f} → {late:.1f} mg/dl")


def check_bolus_returns() -> None:
    bolus = MEAL_G / PROVISIONAL_CR
    none = run_open_loop(
        PATIENT, minutes=MEAL_AT + WINDOW + 1,
        meal_at=MEAL_AT, meal_g=MEAL_G,
    )
    dosed = run_open_loop(
        PATIENT, minutes=MEAL_AT + WINDOW + 1,
        meal_at=MEAL_AT, meal_g=MEAL_G,
        bolus_at=MEAL_AT, bolus_u=bolus,
    )
    peak = max(dosed.glucose[MEAL_AT:MEAL_AT + WINDOW])
    d4_none = at(none, MEAL_AT + WINDOW) - at(none, MEAL_AT)
    d4_dosed = at(dosed, MEAL_AT + WINDOW) - at(dosed, MEAL_AT)
    if peak <= at(dosed, MEAL_AT) + 10:
        raise SystemExit(f"bolused meal should still peak: peak={peak:.1f}")
    if d4_dosed >= d4_none:
        raise SystemExit(
            f"bolus should cut the 4 h rise: Δ4h {d4_dosed:.1f} vs no bolus {d4_none:.1f}"
        )
    print(
        f"ok bolus effect  peak {peak:.1f}  Δ4h {d4_dosed:+.1f} "
        f"(no bolus {d4_none:+.1f})  bolus {bolus:.1f} U"
    )


def check_night_flat() -> None:
    tr = run_open_loop(PATIENT, minutes=360)
    g = tr.glucose
    span = max(g) - min(g)
    sd = statistics.pstdev(g)
    if span > 25 or sd > 8:
        raise SystemExit(f"night should stay flat: span={span:.1f} sd={sd:.1f}")
    print(f"ok night flat   span {span:.1f}  sd {sd:.1f}  start {g[0]:.1f}")


def main() -> int:
    check_night_flat()
    check_meal_rises()
    check_bolus_returns()
    return 0


if __name__ == "__main__":
    sys.exit(main())
