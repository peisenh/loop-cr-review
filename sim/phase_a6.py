"""Phase A.6 — cluster bootstrap of L̂ (patient × gain).

Does not resample rows. Same CSV, no new runs.

    PYTHONPATH=. python3 -m sim.phase_a6 --in sim/phase_a_results.csv
"""

from __future__ import annotations

import argparse
import csv
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def load_clusters(path: Path, gate: str):
    g = defaultdict(list)
    for r in csv.DictReader(path.open(encoding="utf-8")):
        if r["gate"] != gate:
            continue
        if abs(float(r["cr_error"])) < 1e-12:
            continue
        g[(r["patient"], r["gains"])].append((float(r["D"]), float(r["E"])))
    return g


def lhat(pairs):
    den = sum(d * d for d, _ in pairs)
    return sum(d * e for d, e in pairs) / den


def boot(cl, n=2000, seed=1):
    keys = list(cl)
    rng = random.Random(seed)
    xs = []
    for _ in range(n):
        draw = [keys[rng.randrange(len(keys))] for _ in keys]
        pairs = [p for k in draw for p in cl[k]]
        xs.append(lhat(pairs))
    xs.sort()
    return xs


def report(cl, label, n_boot, seed) -> str:
    point = lhat([p for v in cl.values() for p in v])
    xs = boot(cl, n=n_boot, seed=seed)
    lo, hi = xs[int(0.025 * len(xs))], xs[int(0.975 * len(xs))]
    per = sorted(lhat(v) for v in cl.values())
    return (
        f"{label}  clusters={len(cl)}  L̂={point:.3f}\n"
        f"  bootstrap {n_boot}  median {statistics.median(xs):.3f}  "
        f"95% {lo:.3f}…{hi:.3f}\n"
        f"  per cluster  median {statistics.median(per):.3f}  "
        f"{per[0]:.3f}…{per[-1]:.3f}"
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--in", dest="src", type=Path, default=Path("sim/phase_a_results.csv"))
    p.add_argument("--n", type=int, default=2000)
    p.add_argument("--seed", type=int, default=1)
    args = p.parse_args(argv)
    print("A.6  cluster bootstrap of L̂ = Σ(DE)/Σ(D²)  (err≠0)\n")
    print(report(load_clusters(args.src, "pass"), "pass", args.n, args.seed))
    print()
    print(report(load_clusters(args.src, "fail"), "fail", args.n, args.seed))
    print("\nFail interval is not an uptake CI: through-origin R² is 0.11.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
