"""Phase A.3 — why 21/30 fail the neutrality gate.

Reads phase_a_results.csv (err=0 rows). No new simulation.

    PYTHONPATH=. python3 -m sim.phase_a3 --in sim/phase_a_results.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def load_zero(path: Path):
    out = {}
    for r in csv.DictReader(path.open(encoding="utf-8")):
        if float(r["cr_error"]) != 0.0:
            continue
        out[(r["patient"], r["gains"])] = r
    return out


def report(z) -> str:
    lines = ["A.3  E0 at zero CR error (gate |E0|<=0.2 U)",
             f"{'patient':<14} {'CR':>6} {'gains':6} {'E0':>7} {'d4':>7} gate"]
    for i in range(1, 11):
        for g in ("weak", "mid", "strong"):
            r = z[(f"adult#{i:03d}", g)]
            lines.append(
                f"{r['patient']:<14} {float(r['cr_true']):6.1f} {g:6} "
                f"{float(r['E0']):+7.2f} {float(r['d4']):+7.1f} {r['gate']}"
            )
    lines.append("")
    for g in ("weak", "mid", "strong"):
        xs = [float(z[(f"adult#{i:03d}", g)]["E0"]) for i in range(1, 11)]
        n = sum(1 for x in xs if abs(x) <= 0.2)
        pos = sum(1 for x in xs if x > 0)
        lines.append(
            f"{g:6}  pass {n}/10  mean E0 {sum(xs)/10:+.2f}  "
            f"E0>0 in {pos}/10"
        )
    lines.append("")
    for i in range(1, 11):
        n = sum(1 for g in ("weak", "mid", "strong")
                if z[(f"adult#{i:03d}", g)]["gate"] == "pass")
        cr = float(z[(f"adult#{i:03d}", "mid")]["cr_true"])
        lines.append(f"adult#{i:03d}  CR {cr:5.1f}  pass {n}/3")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--in", dest="src", type=Path,
                   default=Path("sim/phase_a_results.csv"))
    args = p.parse_args(argv)
    print(report(load_zero(args.src)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
