"""Empirical loop uptake L (SIMULATION-SPEC §7.1 / §13.3).

    D = CHO/CR_true − CHO/CR_set     insulin shortfall (U)
    E = ∫ (basal − profile) dt       extra basal in the 4 h window (U)
    L = E / D                        only for D ≠ 0

Positive CR error = CR too weak (fewer units per gram).
"""

from __future__ import annotations

from dataclasses import dataclass

from sim.closed_loop import run_closed_loop
from sim.controller import MID, Gains
from sim.cr_true import DEFAULT_MEAL_G, DEFAULT_PATIENT, MEAL_AT, WINDOW, measure


# Same grid as the spec, centred on the known ~15 % threshold.
CR_ERRORS = (-0.30, -0.20, -0.15, -0.10, 0.0, 0.10, 0.15, 0.20, 0.30)


@dataclass(frozen=True)
class Uptake:
    cr_error: float
    cr_set: float
    bolus_u: float
    deficit_u: float
    extra_u: float
    L: float | None
    d4: float


def extra_in_window(tr, start: int, minutes: int) -> float:
    sl = slice(start, start + minutes)
    return sum((b - tr.profile_u_per_hour) / 60.0 for b in tr.basal_u_per_hour[sl])


def delta_4h(tr, start: int, minutes: int) -> float:
    return tr.glucose[start + minutes] - tr.glucose[start]


def one(
    cr_true: float,
    cr_error: float,
    meal_g: float = DEFAULT_MEAL_G,
    patient: str = DEFAULT_PATIENT,
    gains: Gains = MID,
) -> Uptake:
    cr_set = cr_true * (1.0 + cr_error)
    bolus = meal_g / cr_set
    deficit = meal_g / cr_true - bolus
    tr = run_closed_loop(
        patient,
        minutes=MEAL_AT + WINDOW + 1,
        meal_at=MEAL_AT, meal_g=meal_g,
        bolus_at=MEAL_AT, bolus_u=bolus,
        gains=gains,
    )
    extra = extra_in_window(tr, MEAL_AT, WINDOW)
    L = None if abs(deficit) < 1e-6 else extra / deficit
    return Uptake(cr_error, cr_set, bolus, deficit, extra, L, delta_4h(tr, MEAL_AT, WINDOW))


def sweep(gains: Gains = MID) -> list[Uptake]:
    ref = measure()
    return [one(ref.cr_d4, err, gains=gains) for err in CR_ERRORS]


COHORT = ("adult#001", "adult#002", "adult#003")


def cohort(gains: Gains = MID, errors=(0.20, -0.20)):
    rows = []
    for name in COHORT:
        ref = measure(name)
        for err in errors:
            u = one(ref.cr_d4, err, patient=name, gains=gains)
            rows.append((name, ref.cr_d4, u))
    return rows


def main() -> int:

    ref = measure()
    print(
        f"{ref.patient}  CR_true 1:{ref.cr_d4:.1f}  meal {ref.meal_g:.0f} g  "
        f"gains {MID.name}"
    )
    print(f"{'err':>7}  {'CR_set':>7}  {'bolus':>6}  {'D':>6}  {'E':>6}  {'L':>6}  {'Δ4h':>7}")
    rows = []
    for err in CR_ERRORS:
        u = one(ref.cr_d4, err)
        rows.append(u)
        L = "  n/a" if u.L is None else f"{u.L:6.2f}"
        print(
            f"{err*100:+6.0f} %  1:{u.cr_set:4.1f}  {u.bolus_u:5.2f}  "
            f"{u.deficit_u:+5.2f}  {u.extra_u:+5.2f}  {L}  {u.d4:+6.1f}"
        )
    pos = [u.L for u in rows if u.L is not None and u.cr_error > 0]
    neg = [u.L for u in rows if u.L is not None and u.cr_error < 0]
    if pos:
        print(f"L (CR too weak):  {min(pos):.2f} … {max(pos):.2f}  mean {sum(pos)/len(pos):.2f}")
    if neg:
        print(f"L (CR too strong): {min(neg):.2f} … {max(neg):.2f}  mean {sum(neg)/len(neg):.2f}")
    print()
    print("cohort mid, ±20 %")
    for name, cr, u in cohort():
        L = "n/a" if u.L is None else f"{u.L:.2f}"
        print(f"  {name}  CR_true 1:{cr:.1f}  err {u.cr_error*100:+.0f}%  L {L}  E {u.extra_u:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
