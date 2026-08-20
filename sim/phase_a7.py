"""Phase A.7 — is L̂=0.29 an artefact of the 0.2 U gate?

Same CSV. Recompute through-origin L̂ at several |E0| thresholds.

    PYTHONPATH=. python3 -m sim.phase_a7 --in sim/phase_a_results.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

THS = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 1.00)


def load(path: Path):
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    e0 = {}
    for r in rows:
        k = (r["patient"], r["gains"])
        if k not in e0:
            e0[k] = abs(float(r["E0"]))
    return rows, e0


def lhat_r2(pairs):
    ds = [p[0] for p in pairs]
    es = [p[1] for p in pairs]
    den = sum(d * d for d in ds)
    b = sum(d * e for d, e in zip(ds, es)) / den
    my = sum(es) / len(es)
    ss_res = sum((e - b * d) ** 2 for d, e in zip(ds, es))
    ss_tot = sum((e - my) ** 2 for e in es)
    return b, 1.0 - ss_res / ss_tot if ss_tot else 0.0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--in", dest="src", type=Path, default=Path("sim/phase_a_results.csv"))
    args = p.parse_args(argv)
    rows, e0 = load(args.src)
    print("A.7  L̂ vs |E0| gate   (err≠0)\n")
    print(f"{'θ':>6}  pass   L̂     R²     n")
    for th in THS:
        pairs, seen = [], set()
        for r in rows:
            k = (r["patient"], r["gains"])
            if e0[k] > th:
                continue
            if abs(float(r["cr_error"])) < 1e-12:
                continue
            pairs.append((float(r["D"]), float(r["E"])))
            seen.add(k)
        if len(pairs) < 4:
            print(f"{th:6.2f}  {len(seen):2}/30   —")
            continue
        b, r2 = lhat_r2(pairs)
        print(f"{th:6.2f}  {len(seen):2}/30  {b:.3f}  {r2:.3f}  {len(pairs):3}")
    # no gate
    pairs = [
        (float(r["D"]), float(r["E"]))
        for r in rows if abs(float(r["cr_error"])) >= 1e-12
    ]
    b, r2 = lhat_r2(pairs)
    print(f"{'none':>6}  30/30  {b:.3f}  {r2:.3f}  {len(pairs):3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
