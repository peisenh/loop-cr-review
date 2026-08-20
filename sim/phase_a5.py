"""Phase A.5 — E vs D structure, pass / fail / all.

Same CSV, no new runs.

    PYTHONPATH=. python3 -m sim.phase_a5 --in sim/phase_a_results.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def _f(r, k):
    v = r.get(k, "")
    return None if v in ("", None) else float(v)


def load(path: Path):
    rows = []
    for r in csv.DictReader(path.open(encoding="utf-8")):
        rows.append({
            **r,
            "D": _f(r, "D"),
            "E": _f(r, "E"),
            "L": _f(r, "L"),
            "err": float(r["cr_error"]),
        })
    return rows


def through0(ds, es):
    den = sum(d * d for d in ds)
    if den < 1e-18:
        return None, None
    b = sum(d * e for d, e in zip(ds, es)) / den
    my = sum(es) / len(es)
    ss_res = sum((e - b * d) ** 2 for d, e in zip(ds, es))
    ss_tot = sum((e - my) ** 2 for e in es)
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 0.0
    return b, r2


def linreg(ds, es):
    n = len(ds)
    mx, my = sum(ds) / n, sum(es) / n
    den = sum((d - mx) ** 2 for d in ds)
    if den < 1e-18:
        return None
    b = sum((d - mx) * (e - my) for d, e in zip(ds, es)) / den
    a = my - b * mx
    ss_res = sum((e - (a + b * d)) ** 2 for d, e in zip(ds, es))
    ss_tot = sum((e - my) ** 2 for e in es)
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 0.0
    return a, b, r2


def corr(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx < 1e-18 or dy < 1e-18:
        return None
    return num / (dx * dy)


def mad(xs):
    med = statistics.median(xs)
    return statistics.median(abs(x - med) for x in xs)


def pick(rows, gate=None, nonzero=True):
    out = []
    for r in rows:
        if gate and r["gate"] != gate:
            continue
        if nonzero and abs(r["err"]) < 1e-12:
            continue
        if r["D"] is None or r["E"] is None:
            continue
        out.append(r)
    return out


def residual_block(rows, lhat) -> str:
    res = [r["E"] - lhat * r["D"] for r in rows]
    ds = [r["D"] for r in rows]
    es = [r["err"] for r in rows]
    rmse = math.sqrt(sum(x * x for x in res) / len(res))
    c_d = corr(res, ds)
    c_e = corr(res, es)
    lines = [
        f"  residual E−L̂D  med {statistics.median(res):+.3f}  "
        f"mean {statistics.mean(res):+.3f}  MAD {mad(res):.3f}  RMSE {rmse:.3f}",
        f"  corr(res, D) {c_d if c_d is None else f'{c_d:+.3f}'}  "
        f"corr(res, error) {c_e if c_e is None else f'{c_e:+.3f}'}",
    ]
    by_g = defaultdict(list)
    for r, z in zip(rows, res):
        by_g[r["gains"]].append(z)
    for g in ("weak", "mid", "strong"):
        xs = by_g.get(g, [])
        if xs:
            lines.append(
                f"  residual {g:6} n={len(xs):3}  med {statistics.median(xs):+.3f}  "
                f"RMSE {math.sqrt(sum(x*x for x in xs)/len(xs)):.3f}"
            )
    return "\n".join(lines)


def summarise(rows, label) -> str:
    if len(rows) < 2:
        return f"{label}: n={len(rows)}"
    ds, es = [r["D"] for r in rows], [r["E"] for r in rows]
    Ls = [r["L"] for r in rows if r["L"] is not None]
    lhat, r2_0 = through0(ds, es)
    fit = linreg(ds, es)
    lines = [f"{label}  n={len(rows)}"]
    if fit:
        a, b, r2 = fit
        lines.append(f"  E ≈ {a:+.3f} + {b:.3f}·D   R²={r2:.3f}")
    if lhat is not None:
        lines.append(f"  through 0  L̂={lhat:.3f}  R²={r2_0:.3f}")
        lines.append(residual_block(rows, lhat))
    if Ls:
        qs = statistics.quantiles(Ls, n=4) if len(Ls) >= 4 else []
        q = f"  Q1–Q3 {qs[0]:.2f}–{qs[2]:.2f}" if qs else ""
        lines.append(
            f"  L  med {statistics.median(Ls):.2f}  "
            f"mean {statistics.mean(Ls):.2f}  {min(Ls):.2f}…{max(Ls):.2f}{q}"
        )
    return "\n".join(lines)


def by_pg(rows) -> str:
    g = defaultdict(list)
    for r in rows:
        g[(r["patient"], r["gains"])].append(r)
    lines = [f"{'who':<22} n  L̂    R²"]
    for k in sorted(g):
        rs = g[k]
        lhat, r2 = through0([r["D"] for r in rs], [r["E"] for r in rs])
        if lhat is None:
            continue
        lines.append(f"{k[0]} {k[1]:6} {len(rs):2}  {lhat:5.3f}  {r2:.3f}")
    return "\n".join(lines)


def by_gain(rows) -> str:
    lines = []
    for g in ("weak", "mid", "strong"):
        xs = [r for r in rows if r["gains"] == g]
        if len(xs) < 2:
            continue
        lhat, r2 = through0([r["D"] for r in xs], [r["E"] for r in xs])
        lines.append(f"  {g:6} n={len(xs):3}  L̂={lhat:.3f}  R²={r2:.3f}")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--in", dest="src", type=Path, default=Path("sim/phase_a_results.csv"))
    args = p.parse_args(argv)
    rows = load(args.src)
    print("A.5  E vs D   (err≠0 unless noted)\n")
    for label, gate in (("pass", "pass"), ("fail", "fail"), ("all", None)):
        xs = pick(rows, gate=gate)
        print(summarise(xs, label))
        print(by_gain(xs))
        print()
    print("pass, per patient×gain")
    print(by_pg(pick(rows, gate="pass")))
    print("\nfail, per patient×gain (R² only if n>=8)")
    print(by_pg(pick(rows, gate="fail")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
