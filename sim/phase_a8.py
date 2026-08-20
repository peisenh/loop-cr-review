"""Phase A.8 — why 9/30 pass the neutrality gate.

E0 vs patient, PID gain, CR_true. Same CSV, no new runs.

    PYTHONPATH=. python3 -m sim.phase_a8 --in sim/phase_a_results.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

GAINS = ("weak", "mid", "strong")


def load_zero(path: Path):
    z = {}
    for r in csv.DictReader(path.open(encoding="utf-8")):
        if float(r["cr_error"]) != 0.0:
            continue
        z[(r["patient"], r["gains"])] = {
            "E0": float(r["E0"]),
            "cr": float(r["cr_true"]),
            "gate": r["gate"],
            "d4": float(r["d4"]),
        }
    return z


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    if da < 1e-18 or db < 1e-18:
        return None
    return num / (da * db)


def additive_r2(z):
    keys = list(z)
    y = [z[k]["E0"] for k in keys]
    pats = sorted({k[0] for k in keys})
    mean = sum(y) / len(y)

    def row(pat, g):
        r = [1.0, 1.0 if g == "mid" else 0.0, 1.0 if g == "strong" else 0.0]
        for p in pats[1:]:
            r.append(1.0 if pat == p else 0.0)
        return r

    X = [row(k[0], k[1]) for k in keys]
    k = len(X[0])
    A = [[0.0] * (k + 1) for _ in range(k)]
    for xi, yi in zip(X, y):
        for a in range(k):
            A[a][k] += xi[a] * yi
            for b in range(k):
                A[a][b] += xi[a] * xi[b]
    for i in range(k):
        piv = A[i][i]
        if abs(piv) < 1e-12:
            continue
        for j in range(i, k + 1):
            A[i][j] /= piv
        for r in range(k):
            if r == i:
                continue
            f = A[r][i]
            for j in range(i, k + 1):
                A[r][j] -= f * A[i][j]
    beta = [A[i][k] for i in range(k)]
    ss_t = sum((yi - mean) ** 2 for yi in y)
    ss_r = 0.0
    for xi, yi in zip(X, y):
        yh = sum(a * b for a, b in zip(xi, beta))
        ss_r += (yi - yh) ** 2
    return 1.0 - ss_r / ss_t, beta[0], beta[1], beta[2]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--in", dest="src", type=Path, default=Path("sim/phase_a_results.csv"))
    args = p.parse_args(argv)
    z = load_zero(args.src)
    e0s = [v["E0"] for v in z.values()]
    mean = sum(e0s) / len(e0s)
    sst = sum((x - mean) ** 2 for x in e0s)

    print("A.8  E0 at err=0   n=30\n")
    print(f"{'patient':<12} {'CR':>6}  {'weak':>7} {'mid':>7} {'strong':>7}  pass")
    for i in range(1, 11):
        pat = f"adult#{i:03d}"
        cr = z[(pat, "mid")]["cr"]
        cells = []
        npass = 0
        for g in GAINS:
            e = z[(pat, g)]["E0"]
            cells.append(f"{e:+7.2f}")
            if z[(pat, g)]["gate"] == "pass":
                npass += 1
        print(f"{pat:<12} {cr:6.1f}  {' '.join(cells)}  {npass}/3")

    print()
    by_g = defaultdict(list)
    for (pat, g), v in z.items():
        by_g[g].append(v["E0"])
    ssg = 0.0
    for g in GAINS:
        xs = by_g[g]
        m = sum(xs) / len(xs)
        ssg += len(xs) * (m - mean) ** 2
        npass = sum(1 for x in xs if abs(x) <= 0.2)
        print(f"{g:6}  mean E0 {m:+.2f}  {min(xs):+.2f}…{max(xs):+.2f}  pass {npass}/10")

    by_p = defaultdict(list)
    for (pat, g), v in z.items():
        by_p[pat].append(v["E0"])
    ssp = 0.0
    for xs in by_p.values():
        m = sum(xs) / len(xs)
        ssp += len(xs) * (m - mean) ** 2

    r2, mu, bmid, bstr = additive_r2(z)
    print(f"\nvariance of E0:  SS_gain {100*ssg/sst:.0f}%  SS_patient {100*ssp/sst:.0f}%")
    print(f"additive gain+patient  R²={r2:.2f}  "
          f"E0 ≈ {mu:+.2f}  +{bmid:.2f}·mid  +{bstr:.2f}·strong")

    crs = [z[(f"adult#{i:03d}", "mid")]["cr"] for i in range(1, 11)]
    print("corr(E0, CR_true):")
    for g in GAINS:
        xs = [z[(f"adult#{i:03d}", g)]["E0"] for i in range(1, 11)]
        print(f"  {g:6}  {corr(xs, crs):+.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
