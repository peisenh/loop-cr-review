"""Phase A.4 — does CR_eff beat CR_set as an estimator of CR_ref?

CR_eff = CHO / (bolus + E) from the Phase A CSV. No new simulation.

    PYTHONPATH=. python3 -m sim.phase_a4 --in sim/phase_a_results.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from pathlib import Path

CHO = 50.0


def rel_errors(rows):
    out = []
    for r in rows:
        cr = float(r["cr_true"])
        err = float(r["cr_error"])
        extra = float(r["E"])
        cr_set = cr * (1.0 + err)
        bolus = CHO / cr_set
        den = bolus + extra
        if den <= 0.05:
            continue
        cr_eff = CHO / den
        out.append((cr_set / cr - 1.0, cr_eff / cr - 1.0))
    return out


def line(label, pairs) -> str:
    if not pairs:
        return f"{label}: n=0"
    es, ee = zip(*pairs)
    def mae(xs): return sum(abs(x) for x in xs) / len(xs)
    def rmse(xs): return math.sqrt(sum(x * x for x in xs) / len(xs))
    closer = sum(1 for a, b in pairs if abs(a) > abs(b))
    n = len(pairs)
    return (
        f"{label:16} n={n:3}  "
        f"set mae {mae(es)*100:5.1f}%  "
        f"eff mae {mae(ee)*100:5.1f}%  "
        f"eff closer {closer}/{n} ({closer/n:.0%})"
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--in", dest="src", type=Path, default=Path("sim/phase_a_results.csv"))
    args = p.parse_args(argv)
    rows = list(csv.DictReader(args.src.open(encoding="utf-8")))
    print("A.4  relative error vs CR_ref   CHO=%.0f g" % CHO)
    print(line("all", rel_errors(rows)))
    print(line("gate pass", rel_errors([r for r in rows if r["gate"] == "pass"])))
    print(line("gate fail", rel_errors([r for r in rows if r["gate"] == "fail"])))
    print(line("pass coarse", rel_errors(
        [r for r in rows if r["gate"] == "pass" and abs(float(r["cr_error"])) >= 0.15])))
    print(line("pass err=0", rel_errors(
        [r for r in rows if r["gate"] == "pass" and float(r["cr_error"]) == 0])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
