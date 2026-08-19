"""M1 isolation + spec §13.2: no CR error → extra basal near zero."""

from __future__ import annotations

import sys

from sim.closed_loop import run_closed_loop
from sim.controller import CGMOnlyPID, MID
from sim.cr_true import DEFAULT_MEAL_G, MEAL_AT, WINDOW, measure
from sim.physiology import basal_u_per_hour
from simglucose.patient.t1dpatient import T1DPatient


def check_isolation() -> None:
    patient = T1DPatient.withName("adult#001")
    pid = CGMOnlyPID(basal_u_per_hour(patient), target=140.0, gains=MID)
    a = pid.policy(160.0, sample_min=1.0)
    pid.reset()
    b = pid.policy(
        160.0, sample_min=1.0,
        meal=80.0, patient_state="secret", cho=90, cr=4.0, bolus=12.0,
    )
    if a != b:
        raise SystemExit(f"M1 failed: {a} vs {b} when kwargs change")
    print(f"ok isolation   policy={a:.3f} U/h unchanged with meal/state kwargs")


def check_zero_error_extra() -> None:
    cr = measure()
    night = run_closed_loop("adult#001", minutes=180)
    if abs(night.extra_u) > 0.15:
        raise SystemExit(f"night extra basal should be ~0: {night.extra_u:.3f} U")
    meal = run_closed_loop(
        "adult#001",
        minutes=MEAL_AT + WINDOW + 1,
        meal_at=MEAL_AT, meal_g=DEFAULT_MEAL_G,
        bolus_at=MEAL_AT, bolus_u=cr.bolus_d4,
    )
    # Matching bolus: the PID may still nudge, but extra must stay small vs the bolus.
    if abs(meal.extra_u) > 0.35 * cr.bolus_d4:
        raise SystemExit(
            f"matched bolus: extra {meal.extra_u:.2f} U vs bolus {cr.bolus_d4:.2f} U"
        )
    print(
        f"ok extra~0     night {night.extra_u:+.3f} U   "
        f"matched meal {meal.extra_u:+.2f} U (bolus {cr.bolus_d4:.2f} U)"
    )


def main() -> int:
    check_isolation()
    check_zero_error_extra()
    return 0


if __name__ == "__main__":
    sys.exit(main())
