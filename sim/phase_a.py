"""Phase A: one mid-size grid, not Monte Carlo (SIMULATION-SPEC §6).

  3 PID strengths × CR-error grid × a small adult cohort.

L is only printed when the phase-0 gate holds for that (patient, gains):
extra basal at zero CR error is small. Outcome B is not locked here.
"""

from __future__ import annotations

from sim.controller import MID, STRONG, WEAK, Gains
from sim.cr_true import measure
from sim.loop_uptake import one

# Spec grid, slightly thinned so a first pass finishes.
ERRORS = (-0.30, -0.20, -0.15, -0.10, 0.0, 0.10, 0.15, 0.20, 0.30)
GAINS = (WEAK, MID, STRONG)
COHORT = ("adult#001", "adult#002", "adult#005")
E0_MAX = 0.2  # U on a 50 g meal — same gate as UPTAKE.md


def phase0_ok(extra_at_zero: float) -> bool:
    return abs(extra_at_zero) <= E0_MAX


def run(cohort=COHORT, gains_list=GAINS, errors=ERRORS):
    cache = {}
    tables = []
    for name in cohort:
        cache[name] = measure(name)
        for gains in gains_list:
            z = one(cache[name].cr_d4, 0.0, patient=name, gains=gains)
            usable = phase0_ok(z.extra_u)
            rows = []
            for err in errors:
                if err == 0.0:
                    rows.append(z)
                else:
                    rows.append(one(cache[name].cr_d4, err, patient=name, gains=gains))
            tables.append((name, cache[name].cr_d4, gains, usable, z.extra_u, rows))
    return tables


def main() -> int:
    tables = run()
    print(f"phase-0 gate: |E| at 0 % <= {E0_MAX} U")
    for name, cr, gains, usable, e0, rows in tables:
        flag = "PASS" if usable else "fail"
        print(f"\n{name}  CR_true 1:{cr:.1f}  {gains.name}  E0 {e0:+.2f}  {flag}")
        if not usable:
            print("  L not read (phase 0)")
            continue
        print(f"  {'err':>6}  {'L':>6}  {'E':>6}  {'Δ4h':>7}")
        for u in rows:
            L = "   n/a" if u.L is None else f"{u.L:6.2f}"
            print(f"  {u.cr_error*100:+5.0f}%  {L}  {u.extra_u:+5.2f}  {u.d4:+6.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
