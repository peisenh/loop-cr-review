"""Phase A — full adult cohort, three gains, full CR-error grid.

Gate is fixed *before* looking at L (E0_MAX). Every patient × gain × error
is written. Failures stay in the table; they are not dropped from the
cohort.

    PYTHONPATH=. python3 -m sim.phase_a
    PYTHONPATH=. python3 -m sim.phase_a --out sim/phase_a_results.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from sim.controller import MID, STRONG, WEAK
from sim.cr_true import DEFAULT_MEAL_G, measure
from sim.loop_uptake import one

COHORT = tuple(f"adult#{i:03d}" for i in range(1, 11))
GAINS = (WEAK, MID, STRONG)
# Spec grid. ±5 / ±10 are in the same run but flagged as "fine"
# because E/D is noisy when |D| is small.
ERRORS = (
    -0.30, -0.25, -0.20, -0.15, -0.10, -0.05,
    0.0,
    0.05, 0.10, 0.15, 0.20, 0.25, 0.30,
)
FINE = {-0.10, -0.05, 0.05, 0.10}
E0_MAX = 0.2  # U; a priori, 50 g meal
FIELDS = (
    "patient", "cr_true", "gains", "cr_error",
    "D", "E", "L", "d4", "E0", "gate", "band",
)


def gate_ok(e0: float) -> bool:
    return abs(e0) <= E0_MAX


def band(err: float) -> str:
    if err == 0.0:
        return "zero"
    if err in FINE:
        return "fine"
    return "coarse"


def run(out: Path | None = None):
    cache = {}
    rows = []
    writer = fh = None
    if out is not None:
        fh, writer = _open_writer(out)
    try:
      for name in COHORT:
        ref = measure(name)
        cache[name] = ref
        print(f"# {name}  CR_true 1:{ref.cr_d4:.2f}  bolus {ref.bolus_d4:.2f} U",
              flush=True)
        for gains in GAINS:
            z = one(ref.cr_d4, 0.0, meal_g=DEFAULT_MEAL_G,
                    patient=name, gains=gains)
            passed = gate_ok(z.extra_u)
            for err in ERRORS:
                u = z if err == 0.0 else one(
                    ref.cr_d4, err, meal_g=DEFAULT_MEAL_G,
                    patient=name, gains=gains,
                )
                rec = {
                    "patient": name,
                    "cr_true": f"{ref.cr_d4:.4f}",
                    "gains": gains.name,
                    "cr_error": f"{err:.2f}",
                    "D": f"{u.deficit_u:.4f}",
                    "E": f"{u.extra_u:.4f}",
                    "L": "" if u.L is None else f"{u.L:.4f}",
                    "d4": f"{u.d4:.2f}",
                    "E0": f"{z.extra_u:.4f}",
                    "gate": "pass" if passed else "fail",
                    "band": band(err),
                }
                rows.append(rec)
                if writer is not None:
                    writer.writerow(rec)
                    fh.flush()
                L = rec["L"] or "n/a"
                print(
                    f"{name} {gains.name:6} {err*100:+6.1f}%  "
                    f"D {u.deficit_u:+6.2f}  E {u.extra_u:+6.2f}  "
                    f"L {L:>6}  d4 {u.d4:+6.1f}  E0 {z.extra_u:+5.2f}  "
                    f"{rec['gate']}",
                    flush=True,
                )
    finally:
        if fh is not None:
            fh.close()
            print(f"wrote {out} ({len(rows)} rows)", flush=True)
    return rows


def _open_writer(out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    f = out.open("w", newline="", encoding="utf-8")
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    f.flush()
    return f, w


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Path("sim/phase_a_results.csv"))
    args = p.parse_args(argv)
    print(
        f"cohort={len(COHORT)} gains={len(GAINS)} errors={len(ERRORS)} "
        f"E0_MAX={E0_MAX} (gate fixed a priori; all rows kept)",
        flush=True,
    )
    run(out=args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
