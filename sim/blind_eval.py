"""Blind check: known CR error → export → real analyzer.

    PYTHONPATH=. python3 -m sim.blind_eval --days 5 --errors 0,-0.2,0.2 --reps 1
"""

from __future__ import annotations

import argparse
import hashlib
import random
import csv
import tempfile
from collections import defaultdict
from pathlib import Path

from sim.blind_score import deficit_u, is_main, run_seed, score, wanted_slots
from sim.controller import MID, STRONG, WEAK
from sim.cr_true import measure
from sim.export import run_days, write_export

from loop_cr_review import generate_report

GAINS = {"weak": WEAK, "mid": MID, "strong": STRONG}


def run_one(patient, cr_true, err, days, gains, tmp, rep,
            noise_sigma=0.0, seed=1):
    cr_set = cr_true * (1.0 + err)
    out = tmp / f"{patient}_{gains.name}_{err:+.2f}_{days}d_r{rep}"
    rng = random.Random(run_seed(seed, patient, err, days, gains.name, rep))
    write_export(
        run_days(patient, days=days, cr_set=cr_set, gains=gains,
                 noise_sigma=noise_sigma, rng=rng),
        out,
    )
    _html, ctx = generate_report(out, lang="en")
    slots = []
    for s in ctx["slots"]:
        key = s.get("key") or str(s.get("label", "")).lower()
        slots.append({"key": key, "flag": s["flag"], "cls": s.get("cls"),
                           "cre": s.get("cre"), "exc": s.get("exc"),
                           "bol": s.get("bol"),
                           "D": deficit_u(cr_true, err, key)})
    return {"err": err, "days": days, "gains": gains.name, "cr_set": cr_set,
            "slots": slots, "rep": rep}


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", ".").replace("+", "")
    try:
        return float(s.split()[0])
    except ValueError:
        return None


def _floats(s):
    return tuple(float(x) for x in s.split(",") if x.strip())


def _ints(s):
    return tuple(int(x) for x in s.split(",") if x.strip())


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--patient", default="adult#001",
                   help="one name, or comma list: adult#001,adult#002")
    p.add_argument("--days", default="5")
    p.add_argument("--errors", default="0,-0.20,0.20")
    p.add_argument("--gains", default="mid", help="weak,mid,strong")
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--slots", default="breakfast,lunch,dinner",
                   help="which slots to score, e.g. lunch,dinner")
    p.add_argument("--noise", type=float, default=0.0,
                   help="CGM noise sigma in mg/dl (0 = deterministic)")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--sigmas", default="",
                   help="comma list of noise sigmas, e.g. 0,1,2,3,5")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    days, errors = _ints(args.days), _floats(args.errors)
    gain_list = [GAINS[x.strip()] for x in args.gains.split(",") if x.strip()]
    patients = tuple(x.strip() for x in args.patient.split(",") if x.strip())
    slot_names = tuple(x.strip() for x in args.slots.split(",") if x.strip())
    print(f"blind  patients={patients}  slots={slot_names}  reps={args.reps}  noise={args.noise}  seed={args.seed}")
    refs = {name: measure(name) for name in patients}
    print(f"{'d':>3} {'gain':6} {'err':>7} {'rep':>3}  result  slots")
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        sigmas = _floats(args.sigmas) if args.sigmas.strip() else (args.noise,)
        for name in patients:
          ref = refs[name]
          for d in days:
            for g in gain_list:
                for err in errors:
                    for sigma in sigmas:
                      for rep in range(1, args.reps + 1):
                        r = run_one(name, ref.cr_d4, err, d, g, tmp, rep,
                                    noise_sigma=sigma, seed=args.seed)
                        r["noise"] = sigma
                        r["patient"] = name
                        r["result"] = score(err, r["slots"], slot_names)
                        bits = " ".join(
                            f"{s['key']}={s['flag']}" for s in r["slots"] if is_main(s["key"])
                        )
                        extra = ""
                        if args.verbose:
                            bits_ed = []
                            for s in r["slots"]:
                                if not is_main(s["key"]):
                                    continue
                                e, dd = _num(s.get("exc")), _num(s.get("D"))
                                l = None if (e is None or not dd) else e / dd
                                bits_ed.append(
                                    f"{s['key']} E={e} D={None if dd is None else round(dd,2)}"
                                    + (f" L={l:.2f}" if l is not None else "")
                                )
                            extra = " " + " ".join(bits_ed)
                        print(f"{d:3} {g.name:6} σ={r.get('noise', args.noise):g} {err*100:+6.1f}% {rep:3}  {r['result']:5}  {bits}{extra}")
                        rows.append(r)
    bag = defaultdict(list)
    for r in rows:
        bag[(r.get("patient"), r["days"], r["gains"], r.get("noise", args.noise), r["err"])].append(r["result"])
    print(f"\n{'who':12} {'d':>3} {'gain':6} {'σ':>4} {'err':>7}  n  ok fp hit miss wrong")
    for (who, d, g, sigma, err), xs in sorted(bag.items()):
        def c(n):
            return sum(1 for x in xs if x == n)
        print(f"{who:12} {d:3} {g:6} {sigma:4g} {err*100:+6.1f}%  {len(xs)}  {c('ok')} {c('fp')} {c('hit')} {c('miss')} {c('wrong')}")
    if args.out:
        with args.out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["patient", "days", "gains", "err", "rep", "result"])
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k) for k in ("patient", "days", "gains", "err", "rep", "result")})
        print("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
