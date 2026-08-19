"""Measure CR_true with the controller still off (SIMULATION-SPEC §5).

Two definitions, both from the same open-loop meal:

* d4  — bolus B* such that glucose at 4 h is back at the pre-meal value
* auc — bolus that minimises the absolute area between the trace and
        that same baseline over the 4 h window

CR_true = CHO / B*. Neither is a pump setting.
"""

from __future__ import annotations

from dataclasses import dataclass

from sim.physiology import at, run_open_loop

DEFAULT_PATIENT = "adult#001"
DEFAULT_MEAL_G = 50.0
MEAL_AT = 60
WINDOW = 240
# Search band in g/U. S2008 adults sit well inside this.
CR_LO, CR_HI = 3.0, 40.0
D4_TOL_MGDL = 2.0
MAX_ITERS = 24


@dataclass(frozen=True)
class CRTrue:
    patient: str
    meal_g: float
    bolus_d4: float
    cr_d4: float
    delta_4h: float
    bolus_auc: float
    cr_auc: float
    auc: float


def _run(patient: str, meal_g: float, bolus_u: float):
    return run_open_loop(
        patient, minutes=MEAL_AT + WINDOW + 1,
        meal_at=MEAL_AT, meal_g=meal_g,
        bolus_at=MEAL_AT, bolus_u=bolus_u,
    )


def _delta_4h(tr) -> float:
    return at(tr, MEAL_AT + WINDOW) - at(tr, MEAL_AT)


def _auc(tr) -> float:
    g0 = at(tr, MEAL_AT)
    return sum(abs(g - g0) for g in tr.glucose[MEAL_AT:MEAL_AT + WINDOW + 1])


def _bolus_for_cr(meal_g: float, cr: float) -> float:
    return meal_g / cr


def titrate_d4(patient: str = DEFAULT_PATIENT, meal_g: float = DEFAULT_MEAL_G) -> tuple[float, float, float]:
    """Bisection on CR so |Δ4h| < D4_TOL_MGDL. Returns bolus, CR, Δ4h."""
    lo, hi = CR_LO, CR_HI
    best_b, best_cr, best_d = None, None, None
    for _ in range(MAX_ITERS):
        cr = 0.5 * (lo + hi)
        bolus = _bolus_for_cr(meal_g, cr)
        d4 = _delta_4h(_run(patient, meal_g, bolus))
        best_b, best_cr, best_d = bolus, cr, d4
        if abs(d4) <= D4_TOL_MGDL:
            break
        # Positive Δ4h → underdosed → CR too weak (too many g/U) → lower CR.
        if d4 > 0:
            hi = cr
        else:
            lo = cr
    return best_b, best_cr, best_d


def titrate_auc(patient: str = DEFAULT_PATIENT, meal_g: float = DEFAULT_MEAL_G, n: int = 16) -> tuple[float, float, float]:
    """Grid search on CR for minimal |area| vs baseline."""
    best = None
    for i in range(n):
        cr = CR_LO + (CR_HI - CR_LO) * i / (n - 1)
        bolus = _bolus_for_cr(meal_g, cr)
        auc = _auc(_run(patient, meal_g, bolus))
        cand = (auc, bolus, cr)
        if best is None or cand < best:
            best = cand
    auc, bolus, cr = best
    return bolus, cr, auc


def measure(patient: str = DEFAULT_PATIENT, meal_g: float = DEFAULT_MEAL_G) -> CRTrue:
    b_d4, cr_d4, d4 = titrate_d4(patient, meal_g)
    b_auc, cr_auc, auc = titrate_auc(patient, meal_g)
    return CRTrue(
        patient=patient, meal_g=meal_g,
        bolus_d4=b_d4, cr_d4=cr_d4, delta_4h=d4,
        bolus_auc=b_auc, cr_auc=cr_auc, auc=auc,
    )


def main() -> int:
    out = measure()
    print(
        f"{out.patient}  {out.meal_g:.0f} g\n"
        f"  CR_true (Δ4h≈0)  1:{out.cr_d4:.1f}   bolus {out.bolus_d4:.2f} U   "
        f"Δ4h {out.delta_4h:+.1f} mg/dl\n"
        f"  CR_true (min AUC) 1:{out.cr_auc:.1f}   bolus {out.bolus_auc:.2f} U   "
        f"AUC {out.auc:.0f} mg/dl·min"
    )
    rel = abs(out.cr_d4 - out.cr_auc) / out.cr_d4
    print(f"  relative gap between definitions: {rel * 100:.0f} %")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
