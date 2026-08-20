## Uptake definition and interpretation

`D` is the CR-induced insulin shortfall:
`CHO/CR_true − CHO/CR_set`.

`E` is the additional loop basal delivered over the 4-hour window:
the integral of `basal − profile`.

`L = E/D` is therefore the fraction of the CR-induced shortfall supplied as
additional loop basal.

The causal chain is:

CR error → incorrect meal bolus → insulin deficit D → patient physiology →
CGM-only closed-loop controller → additional loop basal E → L = E/D.

`E` is an insulin-delivery quantity. Physiological insulin response is handled
by the S2008 patient model. Thus `L ≈ 0.29` is a measured response of the
simulated controller, not a generator parameter or a physiological absorption
constant.

CamAPS FX Auto Mode was not simulated. Therefore this result must not be
described as "CamAPS has a 29% uptake".

For the gate-pass population the measured result is:

- through-origin `L̂ ≈ 0.29`
- `R² ≈ 0.87`
- cluster-bootstrap 95% interval `0.25–0.35`

The defensible interpretation is: in the independent S2008/PID simulation,
under neutral work-points, additional loop basal is approximately proportional
to the CR-induced insulin shortfall, with a measured uptake fraction around
`L = 0.29`.
# Phase A — close and conclusion

## Preliminary result of the simulation

Under an independent CGM-only controller, extra basal tracks a carb-ratio
shortfall only at some work-points. There, \(E \approx L\cdot D\) with L
about 0.2–0.5 per work-point, not a universal constant. Outside that
neutrality window extra basal barely depends on the shortfall. `CR_eff`
improves on the programmed ratio only in the first case, and only as a
partial correction. The sensitivity generator’s share is not a target and
is not revoked. `LOOP_RATIO` is not retuned from this PID. CamAPS was not
simulated.

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

## Phase A.5 — why fail is not E ≈ L·D

Same CSV, err≠0. `python3 -m sim.phase_a5`.

The intercept-form slope is ~0.29 on **both** sides. Fail differs by a
large offset and scatter: residual RMSE 0.15 (pass) vs 0.91 (fail).
Through the origin, fail R² drops to 0.11 because E0 is already in E.
Strong-gain failures: residual median +1.22 U.

So the 252 fails are not a shallower uptake. They are a biased, noisy
baseline. L̂ from all 360 rows is therefore not a CR factor.

## Phase A.6 — cluster bootstrap of L̂

Resample the 9 passing patient×gain units, not rows.
`python3 -m sim.phase_a6`.

Pass: L̂=0.29, bootstrap 95% **0.25–0.35**. Per cluster 0.22–0.54.
Fail gets a similar interval; that is not uptake (through-origin R²=0.11).

## Phase A.7 — L̂ vs gate threshold

Same CSV. `python3 -m sim.phase_a7`.

θ=0.10…0.30: L̂ stays 0.26–0.29, R² 0.87–0.91. Opening the gate to 0.40
drops R² to 0.63. 0.29 is not an artefact of the 0.2 U cut.

## Mechanistic check

`python3 -m sim.uptake_mech` — off-grid errors and hourly E, same
`closed_loop` path.

On `adult#001` mid, L at 7/18/22 % matches the 10/20/30 % neighbours
(+20 %: L=0.30; −20 %: L=0.19). The 0.29 is not a 5 %-grid artefact.

Hourly extra at ±20 %:

| | +20 % (D=+1.4 U) | −20 % (D=−2.1 U) |
|--|--|--|
| 1 h | E=+1.93 | E=+1.93 |
| 2 h | E=+1.85 | E=+1.39 |
| 3 h | E=+0.58 | E=+0.12 |
| 4 h | E=+0.42 (L=0.30) | E=−0.41 (L=0.19) |

Hour 1 is the meal rise, almost independent of D. Hours 2–4 pay it back.
Net 4 h L is the leftover, not a programmed share of the shortfall.

## Phase A.8 — why 9/30 pass

Same CSV, err=0. `python3 -m sim.phase_a8`.

Gain accounts for **63 %** of E0 variance, patient **18 %**. Together
R²=0.81: E0 ≈ −0.43 (weak) +0.49 mid +1.37 strong. CR_true does not
sort them (corr with E0 ≈ 0).

Only adult#002 passes all three gains. Neutrality is mostly the PID
working point, then who the S2008 adult is.


## Blind runs

`python3 -m sim.blind_eval --patient adult#001,adult#002,adult#007,adult#010 --days 5 --errors=-0.20,0.20 --slots lunch,dinner -v`

The analyzer does not see CR_true. `--reps` without noise is the same trajectory.

### 0 % CR error, 5 days, mid

| Patient | all slots | lunch+dinner only | note |
|--|--|--|--|
| #001 | fp (breakfast weak, E/B 1.20/7.6) | ok | morning extra already at 0 % |
| #002 | ok | ok | quiet |
| #007 | fp (lunch strong, −0.59/2.4) | fp | small bolus (CR 1:25) |
| #010 | ok | ok | quiet |

#001 breakfast stays weak at 3, 5, 7 and 10 days.

### ±20 %, 5 days, mid

Lunch+dinner only: #002 and #010 **miss** both signs. #001 miss. #007 "hit" is the same lunch-strong as at 0 %, plus a dinner-weak at +20 %.

All slots: #001 −20 % is **wrong** (breakfast still weak). +20 % "hits" on #001/#002 go through breakfast; on #001 that flag was already there at 0 %.

Breakfast extra on #001 is 1.21 / 1.20 / 1.34 U at −20 / 0 / +20 % — almost independent of the CR error.

### Reading

On quiet slots the analyzer does not see a 20 % CR error. Where it fires, the 0 % run was often already unquiet. Not a CamAPS result. Analyzer unchanged.

### Noisy 0 % and ±20/±30 % (Phase B first slice)

`--noise 5 --seed 1 --reps 5 --slots lunch,dinner --days 5`, mid.

| | #002 | #010 |
|--|--|--|
| 0 % | 5/5 ok | 5/5 ok |
| −30, −20, +20, +30 % | 0/20 hit | 0/20 hit |

40/40 miss. Extra/bolus typically 0.02–0.06. FPR is 0; detection does not
beat it. This slice **fails** the pre-registered Phase B gate.

### Noise sweep (why 0/40)

Same cell: `adult#002` mid, +20 %, 5 days, lunch+dinner, seed 1.

| σ | n | hit | lunch E / D / L at rep 1 |
|--:|--:|--:|--|
| 0 | 5 | 0/5 | 0.72 / 1.31 / 0.55 |
| 1 | 5 | 2/5 | 0.80 / 1.31 / 0.61 |
| 5 | 5 | 0/5 | 0.16 / 1.31 / 0.12 |

σ=0 is deterministic (five copies). E vs D is there (L≈0.55); extra/bolus
stays under the verdict rule (~0.11). σ=1 is threshold jitter, not a
detection curve. σ=5 shrinks E. Both effects explain the 0/40 slice.

`blind_eval --sigmas 0,1,5` prints E and D. Seeds are SHA-256.

## Robustness exit — simulation frozen

`python3 -m sim.robust_check`. Criteria in [PHASE_B_ROBUST.md](PHASE_B_ROBUST.md).

1. Same seed, two processes: **PASS** (identical stdout).
2. Seeds 1001/1002/1003, #002 +20 %, lunch+dinner: σ=0 always L≈0.55 and
   miss; σ=1 miss on these seeds; σ=5 extra gone. Reading unchanged.
3. Boundary, 1 rep, lunch+dinner:

| | 0 % σ=0/1/5 | +20 % | +30 % σ=0 | +30 % σ=5 |
|--|--|--|--|--|
| #002 | ok / ok / ok | miss / hit / miss | hit | miss |
| #010 | ok / ok / ok | miss / miss / miss | hit | miss |

**Exit:** E vs D is stable; the verdict at 20 % is not. 0 % stays quiet.
+30 % shows the signal only while noise is small. Do not retune the
analyzer. No further B factorial. Not CamAPS.

## Final conclusion

Phase A (physiology, gate, E≈L·D) and Phase B (blind analyzer, noise,
exit check) are closed. The simulation is **frozen**.

| Layer | Finding |
|--|--|
| Mechanism | On quiet work-points, extra basal tracks a CR shortfall (L roughly 0.25–0.55). E is *delivered* pump insulin, not body uptake. |
| Analyzer | On those same quiet slots the verdict often does not fire at ±20 % because extra/bolus stays under the fixed rule. |
| Noise | σ=5 shrinks E; detection does not improve. |
| Tool | `loop_cr_review` is discussion material. Extra basal is a CR cue only when the loop is already quiet without a meal. Not a CamAPS result. Do not retune the analyzer from this PID. |

Specs: [SIMULATION-SPEC.md](SIMULATION-SPEC.md) · [PHASE_B_DESIGN.md](PHASE_B_DESIGN.md) · [PHASE_B_ROBUST.md](PHASE_B_ROBUST.md).
