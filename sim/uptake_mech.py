"""Mechanistic uptake check — not another fit on the 13-point grid.

For a few work-points: off-grid CR errors, hourly share of E, E vs D
split by sign. L comes from the same closed_loop path as Phase A.

    PYTHONPATH=. python3 -m sim.uptake_mech
"""

from __future__ import annotations

from sim.closed_loop import run_closed_loop
from sim.controller import MID, Gains, WEAK, STRONG
from sim.cr_true import DEFAULT_MEAL_G, MEAL_AT, WINDOW, measure
from sim.loop_uptake import extra_in_window, one

# Points that are *not* on the Phase A 5 % grid.
OFF_GRID = (-0.22, -0.18, -0.07, 0.07, 0.18, 0.22)
ON_GRID = (-0.30, -0.20, -0.10, 0.10, 0.20, 0.30)
HOURS = (60, 120, 180, 240)

WORK = (
    ("adult#001", MID),
    ("adult#002", MID),
    ("adult#007", MID),
)


def hourly(patient: str, cr_true: float, err: float, gains: Gains, meal_g=DEFAULT_MEAL_G):
    cr_set = cr_true * (1.0 + err)
    bolus = meal_g / cr_set
    d = meal_g / cr_true - bolus
    tr = run_closed_loop(
        patient,
        minutes=MEAL_AT + WINDOW + 1,
        meal_at=MEAL_AT, meal_g=meal_g,
        bolus_at=MEAL_AT, bolus_u=bolus,
        gains=gains,
    )
    cum = []
    for h in HOURS:
        e = extra_in_window(tr, MEAL_AT, h)
        cum.append(None if abs(d) < 1e-6 else e / d)
    return d, extra_in_window(tr, MEAL_AT, WINDOW), cum


def main() -> int:
    print("Mechanistic check  meal=50 g  window=4 h\n")
    print("Off-grid vs on-grid L (same closed_loop):")
    for name, gains in WORK:
        ref = measure(name)
        print(f"\n{name}  {gains.name}  CR_true 1:{ref.cr_d4:.1f}")
        print(f"  {'err':>7}  {'D':>6}  {'E':>6}  {'L':>6}  L1h  L2h  L3h  L4h")
        for err in OFF_GRID + ON_GRID:
            u = one(ref.cr_d4, err, patient=name, gains=gains)
            d, e, cum = hourly(name, ref.cr_d4, err, gains)
            c = " ".join("---" if x is None else f"{x:.2f}" for x in cum)
            L = "---" if u.L is None else f"{u.L:.3f}"
            print(f"  {err*100:+6.1f}%  {u.deficit_u:+6.2f}  {u.extra_u:+6.2f}  {L:>6}  {c}")
    print(
        "\nIf L at 7/18/22 % matches the 10/20/30 % neighbours, the 0.29 "
        "is not a grid artefact. On adult#001 mid, hour 1 extra is ~+1.9 U "
        "for both +20 % and -20 % (meal rise, not D). Hours 2-4 give the "
        "extra back; 4 h net L is the leftover. So 0.29 is a residual after "
        "a biphasic meal response, not a set share of the deficit."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
