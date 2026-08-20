<!--
SPDX-FileCopyrightText: 2026 Peter Eisenhauer
SPDX-License-Identifier: CC-BY-SA-4.0
-->

# Phase B design — blind method check

Status: **design only**. No large B runner yet. A first deterministic
slice already exists (`sim/blind_eval.py`, results in
[UPTAKE.md](UPTAKE.md) § Blind runs).

Does not change `loop_cr_review.py`. Companion to
[SIMULATION-SPEC.md](SIMULATION-SPEC.md) (M1–M4 still apply).

---

## Hypothesis

If a carb-ratio error is large enough, extra basal in the post-meal
window lets the analyzer flag the right direction more often than it
false-alarms at zero error.

Pre-registered, not fitted after the grid.

## What B is not

- Not a CamAPS FX replica.
- Not S2008 as a truth machine. S2008 is weak in hypoglycaemia; B stays
  in the normal-to-high glucose band. Hypos are a later, separate slice.
- Not another regression on `phase_a_results.csv`.
- Not a controller built to emit `LOOP_RATIO` extra.

## Data path

```
known CR_true, chosen CR_set
        → meal + bolus = CHO / CR_set
        → independent controller
        → CGM + insulin + CHO  (no CR_true)
        → loop_cr_review.generate_report
        → flags / CR_eff
        → compare to CR_true
```

Manipulate the **bolus**, not the analyzer.

## Controllers

| | May see | Role |
|--|--|--|
| **B** (default) | CGM only, plus basal profile at setup (M1) | Same class as Phase A PID |
| **A** (later) | extra state (IOB / meal) | Contrast: if only A works, the method needs an unrealistic loop |

Do not start A until B has a 0 % false-positive number.

## Ground truth

- `CR_true` = measured Δ4h titration (`sim.cr_true`), not a guess.
- Error = `CR_set / CR_true − 1`.
- Slot class as the analyzer’s `cls` (`weak` / `strong` / `ok`).
- Primary slots for the first B slice: **lunch and dinner**. Breakfast
  on adult#001 already false-alarms at 0 % (meal-driven extra).

## First slice (do this before 500-rep factorial)

Already run, deterministic, mid PID, 5 days:

- 0 %: #002/#010 ok; #001 breakfast fp; #007 lunch fp.
- ±20 % on lunch+dinner: miss on the two quiet adults.

Next B increment, still small:

1. Same four adults, mid, 5 days, add **process/CGM noise** so replicates
   differ.
2. Errors `-0.30,-0.20,0,-0.20,0.30` (write `--errors=-0.30,...`).
3. Report lunch+dinner and all-slots separately.
4. Stop if 0 % lunch+dinner FPR on the quiet adults is already high
   under noise.

## Later ceiling (not the next commit)

10 adults × 3 gains × 7 errors × 5 day-lengths × many replicates.
Only after the noisy 0 % row is readable. Two-controller contrast after
that.

## Pass / fail (fixed now)

On **lunch+dinner**, patients that were quiet at 0 % without noise
(#002, #010 mid), with noise, 5 days:

| | Fail B if |
|--|--|
| 0 % | more than **1 in 5** replicates has a non-ok lunch or dinner |
| ±20 % | detection no better than that 0 % false-positive rate |
| ±30 % | same: must beat the 0 % FPR |

A “hit” that appears only on a slot that was already wrong at 0 % does
not count.

Hypos, children, other physiology: out of scope; no pass/fail.

## Outputs

- Table: error × days × patient × gain → FPR / hit / miss / wrong.
- `CR_eff` bias vs `CR_true` and vs `CR_set` (same question as A.4).
- Note S2008 + this PID, not CamAPS.

## Implementation notes

Reuse `sim/export.py`, `sim/blind_eval.py`, `sim/blind_score.py`.
Add noise in the generator, not in the analyzer. Keep the controller
isolated (existing `check_controller` test).
