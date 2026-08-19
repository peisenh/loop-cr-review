"""Phase A.2 — apply the analysis LOOP_RATIO to simulated extra/bolus.

No new simulation. Reads phase_a_results.csv.

    ratio = E / bolus
    |ratio| > 0.12  →  same verdict as loop_cr_review

    PYTHONPATH=. python3 -m sim.phase_a2 --in sim/phase_a_results.csv
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

# Import the rule instead of restating it: a local copy would drift silently
# if the tool's threshold ever changes. Evaluation may depend on the analysis;
# the simulation itself (sim/export.py, sim/closed_loop.py) may not.
from loop_cr_review import LOOP_RATIO, verdict_class

CHO = 50.0


def verdict(ratio: float) -> str:
    return verdict_class(ratio * 1.0, 1.0, 0.0)   # same rule as the report


def truth(err: float) -> str:
    if err > 0:
        return "weak"
    if err < 0:
        return "strong"
    return "ok"


def load(path: Path):
    rows = []
    for r in csv.DictReader(path.open(encoding="utf-8")):
        err = float(r["cr_error"])
        cr = float(r["cr_true"])
        extra = float(r["E"])
        bolus = CHO / (cr * (1.0 + err))
        ratio = extra / bolus
        L = None if not r.get("L") else float(r["L"])
        rows.append({
            **r,
            "bolus": bolus,
            "ratio": ratio,
            "verdict": verdict(ratio),
            "truth": truth(err),
            "Lnum": L,
        })
    return rows


def table(rows, gate="pass") -> str:
    by = defaultdict(list)
    for r in rows:
        if gate != "all" and r["gate"] != gate:
            continue
        by[float(r["cr_error"])].append(r)
    lines = [
        f"gate={gate}  LOOP_RATIO={LOOP_RATIO}  CHO={CHO:g} g",
        f"{'err':>7}  {'n':>3}  {'hit':>5}  weak  ok  strong  med E/B  med L",
    ]
    for err in sorted(by):
        xs = by[err]
        hit = sum(1 for r in xs if r["verdict"] == r["truth"]) / len(xs)
        nw = sum(1 for r in xs if r["verdict"] == "weak")
        no = sum(1 for r in xs if r["verdict"] == "ok")
        ns = sum(1 for r in xs if r["verdict"] == "strong")
        rats = sorted(r["ratio"] for r in xs)
        Ls = [r["Lnum"] for r in xs if r["Lnum"] is not None]
        medL = "   —" if not Ls else f"{statistics.median(Ls):5.2f}"
        lines.append(
            f"{err*100:+6.1f}%  {len(xs):3}  {hit:5.0%}  "
            f"{nw:4} {no:3} {ns:6}  {statistics.median(rats):+7.3f}  {medL}"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--in", dest="src", type=Path, default=Path("sim/phase_a_results.csv"))
    p.add_argument("--gate", default="pass", choices=("pass", "fail", "all"))
    args = p.parse_args(argv)
    rows = load(args.src)
    print(table(rows, gate=args.gate))
    return 0


if __name__ == "__main__":
    sys.exit(main())
