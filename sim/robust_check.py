"""Phase B exit: reproducibility and small perturbations.

Not a new factorial. Same analyzer, same generator.

    PYTHONPATH=. python3 -m sim.robust_check --repro
    PYTHONPATH=. python3 -m sim.robust_check --seeds
    PYTHONPATH=. python3 -m sim.robust_check --boundary

--repro: two processes, same seed, compare result lines.
--seeds: seeds 1001/1002/1003 at σ=0,1,5 on #002 +20 % lunch+dinner, 1 rep.
--boundary: #002 and #010 × {0,+20,+30}% × σ={0,1,5}, 1 rep.

Pass (pre-registered): same seed → identical; other seeds do not flip the
qualitative reading; 0 % stays quiet; +30 % still shows E vs D; +20 % may
jitter.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str]) -> str:
    env = {**dict(**{k: v for k, v in __import__("os").environ.items()}),
           "PYTHONPATH": str(ROOT)}
    p = subprocess.run(
        [sys.executable, "-m", "sim.blind_eval", *args],
        cwd=ROOT, env=env, capture_output=True, text=True, check=True,
    )
    return p.stdout


def _result_lines(out: str) -> list[str]:
    return [ln for ln in out.splitlines() if ln.strip()[:1].isdigit() or
            (len(ln) > 4 and ln[4:5].isdigit())]


def cmd_repro() -> int:
    args = [
        "--patient", "adult#002", "--days", "5", "--errors=0.20",
        "--slots", "lunch,dinner", "--reps", "1", "--noise", "1",
        "--seed", "12345",
    ]
    a, b = _run(args), _run(args)
    la, lb = a.splitlines(), b.splitlines()
    if a == b:
        print("repro PASS: two processes, seed 12345, identical stdout")
        return 0
    print("repro FAIL")
    for x, y in zip(la, lb):
        if x != y:
            print(" -", x)
            print(" +", y)
    return 1


def cmd_seeds() -> int:
    print("seeds  #002 +20% lunch+dinner  1 rep")
    for seed in (1001, 1002, 1003):
        for sig in (0, 1, 5):
            out = _run([
                "--patient", "adult#002", "--days", "5", "--errors=0.20",
                "--slots", "lunch,dinner", "--reps", "1",
                "--sigmas", str(sig), "--seed", str(seed), "-v",
            ])
            for ln in out.splitlines():
                if "σ=" in ln or (ln[:1].isdigit()):
                    print(f"seed={seed}", ln)
                    break
            else:
                print(out[-400:])
    return 0


def cmd_boundary() -> int:
    print("boundary  #002/#010  err 0/+20/+30  σ 0/1/5")
    for who in ("adult#002", "adult#010"):
        for err in ("0", "0.20", "0.30"):
            out = _run([
                "--patient", who, "--days", "5", f"--errors={err}",
                "--slots", "lunch,dinner", "--reps", "1",
                "--sigmas", "0,1,5", "--seed", "1", "-v",
            ])
            print(out)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--repro", action="store_true")
    g.add_argument("--seeds", action="store_true")
    g.add_argument("--boundary", action="store_true")
    args = p.parse_args(argv)
    if args.repro:
        return cmd_repro()
    if args.seeds:
        return cmd_seeds()
    return cmd_boundary()


if __name__ == "__main__":
    raise SystemExit(main())
