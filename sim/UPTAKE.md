# Phase A — close and conclusion

Non-circular check: extra basal comes from a CGM-only PID. Formal adult
grid: 10 S2008 adults × weak/mid/strong × CR error −30…+30 % (390 rows).
Gate `|E₀| ≤ 0.2 U` is fixed before L is read. Reproduce:

```bash
PYTHONPATH=. python3 -m sim.phase_a --out sim/phase_a_results.csv
```

## Three levels (do not collapse)

| Level | Claim |
|-------|--------|
| All 30 patient×gain | **9 pass / 21 fail** the neutrality gate. The 21 failures *are* the result. |
| Gate population | On the coarse band (\|error\| ≥ 15 %), L ≈ **0.2–0.55** (mean ~0.33 too-weak, ~0.38 too-strong). That measured L is the uptake figure, not a generator parameter. |
| Fail population | L is not a CR signal (`E/D` from about −4 to +6). |

Only adult#002 passes all three gains. Mid: 5/10. Weak/strong: 2/10 each.

## Gate sensitivity (same CSV, no new runs)

| θ (U) | pass | mid | weak | strong |
|------|------|-----|------|--------|
| 0.10 | 5/30 | 5 | 0 | 0 |
| 0.20 | 9/30 | 5 | 2 | 2 |
| 0.30 | 9/30 | 5 | 2 | 2 |

0.20 and 0.30 select the same set. 0.10 keeps only mid. Mean L stays ~0.3–0.4;
L stays in that band at 0.10 and 0.30 U as well. `|E₀|` median is ~0.40; 21/30 already exceed 0.3 U.

## Fine grid (±5 / ±10 %)

L jumps because the shortfall D is small, not because a new mechanism appears.
Read L on the coarse band.

## Conclusion

- Measured L on the gate population is stable enough to test the method here;
  it is not a constant across all 30 work-points.
- `LOOP_SHARE` in `validate_sensitivity.py` is a generator setting, not a
  target. Phase A does not revoke that statistical test.
- Do **not** change `LOOP_RATIO` (report threshold ≠ uptake).
- Working reading: **B/C border** — a CR-linked extra basal exists in a
  minority of work-points; it is not a general calibration. That is not a
  hard ban on Phase B. A full factorial is still the wrong next step;
  varying one kinetic factor on a few patients could separate “PID not
  neutral” from “no CR signal”.

The question Phase A answers is whether L is stable enough for an independent
check of the method: yes on the gate population, not on the full 30.

## Phase A.2 — LOOP_RATIO on simulated E/bolus

Same rule as `loop_cr_review`: `ratio = E / bolus`, threshold 0.12.
No new runs; `python3 -m sim.phase_a2 --in sim/phase_a_results.csv`.

Gate-pass only (n=9 per error step):

| CR error | hit | weak | ok | strong | med E/B | med L |
|---------:|----:|-----:|---:|-------:|--------:|------:|
| −30 % | 33 % | 0 | 6 | 3 | −0.103 | 0.34 |
| −20 % | 22 % | 0 | 7 | 2 | −0.065 | 0.32 |
| −15 % | 11 % | 0 | 8 | 1 | −0.045 | 0.30 |
| 0 % | 100 % | 0 | 9 | 0 | +0.005 | — |
| +15 % | 0 % | 0 | 9 | 0 | +0.057 | 0.38 |
| +20 % | 0 % | 0 | 9 | 0 | +0.072 | 0.36 |
| +30 % | 44 % | 4 | 5 | 0 | +0.106 | 0.35 |

At zero error the 0.12 threshold does not false-alarm. With L ≈ 0.3–0.4,
E/B stays below 0.12 until the CR error is large, so the tool mostly says
ok. E/bolus follows the measured L, not the generator. Do not retune
`LOOP_RATIO` from this PID.
