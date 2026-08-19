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
| Gate population | On the coarse band (\|error\| ≥ 15 %, n=72): median **0.33**, quartiles 0.24–0.49, full range **−0.19 … 0.80**. 28 % of points fall outside 0.2–0.55, and two are negative (`adult#004 weak`, +15/+20 %: extra basal runs *against* the shortfall). Mean 0.33 too-weak / 0.38 too-strong. That measured L is the uptake figure, not a generator parameter. |
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

**Asymmetry hypothesis: not confirmed here.** Median E/B is −0.103 at −30 % and +0.106 at +30 % — near symmetric, no saturation visible in this range. It was pre-registered as refutable, so this is reported as it stands. Note also that the hit rates below rest on n=9 per step: 33 % is three cases.

At zero error the 0.12 threshold does not false-alarm. With L ≈ 0.3–0.4,
E/B stays below 0.12 until the CR error is large, so the tool mostly says
ok. E/bolus follows the measured L, not the generator. Do not retune
`LOOP_RATIO` from this PID.

## Export path — end to end through the real readers

`sim/export.py` writes a Glooko-style export (BOM, German decimal comma, 5-min
CGM grid, 10-min basal segments, `Insulin data/` subfolder), so a simulated run
goes through the **actual** readers, fasting-basal reference and slot logic
rather than a simulation-only shortcut.

```bash
PYTHONPATH=. python3 -c "
from pathlib import Path
from sim.export import run_days, write_export
write_export(run_days(days=5, cr_set=5.89), Path('/tmp/exp'))"
python3 loop_cr_review.py /tmp/exp -o /tmp/exp.html
```

First result, `adult#001`, mid gains, 5 days, 45 g meals, `CR_ref_Δ4h = 5.89`:

| CR_set | verdict per slot | CR_eff (breakfast/lunch/dinner) |
|---|---|---|
| 5.89 (correct) | ok / ok / ok | 5.3 / 6.1 / 5.7 — mean 5.7 vs ref 5.89 (≈3 % off) |
| 7.36 (25 % too weak) | **weak** / ok / ok | 6.2 / 7.3 / 6.6 — mean 6.7 |

Two things follow. At a correctly set ratio the tool does **not** false-alarm and
`CR_eff` lands close to the measured reference. At a 25 % error `CR_eff` closes
only about **45 % of the gap** between setting and reference (7.36 → 6.7 of the
way to 5.89) and one slot in three crosses the threshold — which is what an
uptake of L ≈ 0.35 predicts: the loop absorbs part of the shortfall, so `CR_eff`
is a partial correction, not the needed ratio.

Caveat: one patient, one gain setting, five days, three slots. This is a working
demonstration that the path is closed and the quantities are consistent, not a
detection statistic.

## Phase A.3 — why 21/30 fail the gate

Same CSV, zero-error rows only: `python3 -m sim.phase_a3`.

E0 shifts with gain: weak mean −0.40 (pass 2/10), mid +0.10 (5/10),
strong +0.97 (2/10). Weak under-delivers, strong over-delivers; Δ4h
goes more negative as the gain rises.

Only adult#002 passes all three gains. #003, #006, #009 pass none.
CR_true does not sort them (#009 at 1:3.9 and #003 at 1:11.7 both fail
all three; #007 at 1:25 still passes mid).

So gate failure is both PID working point and S2008 heterogeneity.
Extra basal is not a general CR signal under this controller.

## Phase A.3 close — is E proportional to D?

Same 390 rows, no new runs. Drop err=0 (D=0). Fit `E ≈ a + L̂·D`.

| set | n | a | L̂ | R² |
|-----|--:|--:|----:|---:|
| gate pass | 108 | +0.02 | **0.29** | **0.87** |
| gate fail | 252 | +0.33 | 0.29 | **0.22** |
| pass, CR too weak | 54 | −0.01 | 0.36 | 0.76 |
| pass, CR too strong | 54 | −0.14 | 0.20 | 0.68 |

Through the origin, pass: L̂=0.29, R²=0.87.

Per passing patient×gain (12 errors each): R² 0.99–1.00, but L̂ from
0.23 (`adult#001` mid) to 0.53 (`adult#007` mid).

There *is* an uptake relation, only behind the gate, and L is per
work-point, not universal. That closes A.3. Do not set `LOOP_RATIO` from it.

## Phase A.4 — does CR_eff beat CR_set?

`CR_eff = CHO/(bolus+E)` from the same CSV. Relative error vs `CR_ref`.

    python3 -m sim.phase_a4 --in sim/phase_a_results.csv

| set | n | mae CR_set | mae CR_eff | CR_eff closer |
|-----|--:|----------:|----------:|--------------:|
| all | 390 | 16.2 % | 14.7 % | 59 % |
| gate pass | 117 | 16.2 % | **10.8 %** | **87 %** |
| gate fail | 273 | 16.2 % | 16.3 % | 47 % |
| pass, \|error\|≥15 % | 72 | 22.5 % | **14.6 %** | **97 %** |
| pass, error=0 | 9 | 0 % | 2.3 % | 0/9 |

Behind the gate, CR_eff is a *partial* correction: better than the programmed
ratio, not the true ratio. Outside the gate it does not help. At zero error
the set is already the ref, so CR_eff can only add noise (here 2 %).

Do not retune `LOOP_RATIO`. The method has a use where the work-point is
neutral, and none where it is not.
