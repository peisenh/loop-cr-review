"""Blind check: known CR error → export → real analyzer.

    PYTHONPATH=. python3 -m sim.blind_eval --days 5 --errors 0,-0.2,0.2 --reps 1
"""

from __future__ import annotations

import argparse
import csv
import tempfile
from collections import defaultdict
from pathlib import Path

from sim.blind_score import is_main, score
from sim.controller import MID, STRONG, WEAK
from sim.cr_true import measure
from sim.export import run_days, write_export

from loop_cr_review import generate_report

GAINS = {"weak": WEAK, "mid": MID, "strong": STRONG}


def run_one(patient, cr_true, err, days, gains, tmp, rep):
    cr_set = cr_true * (1.0 + err)
    out = tmp / f"{patient}_{gains.name}_{err:+.2f}_{days}d_r{rep}"
    write_export(run_days(patient, days=days, cr_set=cr_set, gains=gains), out)
    _html, ctx = generate_report(out, lang="en")
    slots = []
    for s in ctx["slots"]:
        key = s.get("key") or str(s.get("label", "")).lower()
        slots.append({"key": key, "flag": s["flag"], "cls": s.get("cls"),
                           "cre": s.get("cre"), "exc": s.get("exc"),
                           "bol": s.get("bol")})
    return {"err": err, "days": days, "gains": gains.name, "cr_set": cr_set,
            "slots": slots, "rep": rep, "result": score(err, slots)}


def _floats(s):
    return tuple(float(x) for x in s.split(",") if x.strip())


def _ints(s):
    return tuple(int(x) for x in s.split(",") if x.strip())


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--patient", default="adult#001")
    p.add_argument("--days", default="5")
    p.add_argument("--errors", default="0,-0.20,0.20")
    p.add_argument("--gains", default="mid", help="weak,mid,strong")
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    days, errors = _ints(args.days), _floats(args.errors)
    gain_list = [GAINS[x.strip()] for x in args.gains.split(",") if x.strip()]
    ref = measure(args.patient)
    print(f"blind  {args.patient}  CR_true 1:{ref.cr_d4:.2f}  reps={args.reps}")
    print(f"{'d':>3} {'gain':6} {'err':>7} {'rep':>3}  result  slots")
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for d in days:
            for g in gain_list:
                for err in errors:
                    for rep in range(1, args.reps + 1):
                        r = run_one(args.patient, ref.cr_d4, err, d, g, tmp, rep)
                        bits = " ".join(
                            f"{s['key']}={s['flag']}" for s in r["slots"] if is_main(s["key"])
                        )
                        extra = ""
                        if args.verbose:
                            extra = " " + " ".join(
                                f"{s['key']} E/B={s.get('exc')}/{s.get('bol')}"
                                for s in r["slots"] if is_main(s["key"])
                            )
                        print(f"{d:3} {g.name:6} {err*100:+6.1f}% {rep:3}  {r['result']:5}  {bits}{extra}")
                        rows.append(r)
    bag = defaultdict(list)
    for r in rows:
        bag[(r["days"], r["gains"], r["err"])].append(r["result"])
    print(f"\n{'d':>3} {'gain':6} {'err':>7}  n  ok fp hit miss wrong")
    for (d, g, err), xs in sorted(bag.items()):
        def c(n):
            return sum(1 for x in xs if x == n)
        print(f"{d:3} {g:6} {err*100:+6.1f}%  {len(xs)}  {c('ok')} {c('fp')} {c('hit')} {c('miss')} {c('wrong')}")
    if args.out:
        with args.out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["days", "gains", "err", "rep", "result"])
            w.writeheader()
            for r in rows:
                w.writerow({k: r[k] for k in ("days", "gains", "err", "rep", "result")})
        print("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
