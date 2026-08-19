# Empirical loop uptake — Phase A (adults) done

Full grid: 10 S2008 adults × weak/mid/strong × CR error −30…+30 %
(13 steps). Gate fixed a priori: |E| at 0 % error ≤ 0.2 U. Every
patient×gain stays in the table (`sim/phase_a.py` → CSV, not committed).

```bash
PYTHONPATH=. python3 -m sim.phase_a --out sim/phase_a_results.csv
```

## Gate (30 combinations)

| | weak | mid | strong |
|--|------|-----|--------|
| pass | 2/10 | 5/10 | 2/10 |

9/30 pass. Only adult#002 passes all three gains. Failures are reported,
not dropped.

## L on the coarse band (|error| ≥ 15 %), gate = pass

About 0.2–0.55; mean ~0.33 (CR too weak) and ~0.38 (CR too strong).
70/72 those cells have L > 0. Where the gate fails, L ranges from −4 to +6.

`LOOP_SHARE = 0.7` is not a stable number on this grid. Do not change
`LOOP_RATIO`. Do not start Phase B (absorption / insulin kinetics) from this:
most work-points already fail at zero CR error.

## Pilot notes below are superseded by the CSV for the adult grid.

## Phase 0 (pilot, historical)
 (gate before L is read)

|E| at zero CR error ≲ 0.2 U on a 50 g meal. Otherwise the PID is already
driving the patient and L is not about the meal.

## Adults 001–010, mid PID

| Patient | CR_true | E0 | L −15 % | L +15 % | Gate |
|---------|---------|-----|---------|---------|------|
| #001 | 1:5.9 | +0.04 | 0.19 | 0.30 | pass |
| #002 | 1:7.6 | +0.09 | 0.31 | 0.50 | pass |
| #003 | 1:11.7 | +0.37 | — | — | fail |
| #004 | 1:21.5 | +0.71 | — | — | fail |
| #005 | 1:6.2 | +0.10 | 0.19 | 0.38 | pass |
| #006 | 1:8.5 | −0.40 | — | — | fail |
| #007 | 1:25.0 | −0.01 | 0.55 | 0.48 | pass |
| #008 | 1:16.9 | −0.40 | — | — | fail |
| #009 | 1:3.9 | +0.52 | — | — | fail |
| #010 | 1:5.3 | −0.05 | 0.26 | 0.23 | pass |

Five of ten pass. On those, L is about **0.2–0.55**, both signs, not 0.7.
Extreme CR_true alone does not decide the gate (#007 passes).

### Gains (slice on #001 / #002 / #005)

Only #002 stays in gate for weak / mid / strong; then L is almost
gain-independent. On #001 and #005 only mid is usable.

### Error grid on the five passers (mid)

±5 %: L jumps (0.04–0.68) because the shortfall is tiny. From about ±10 %
L settles in the 0.2–0.55 band. #007 can look flat in L while Δ4h stays
deeply negative — E-gate alone does not make the glucose story healthy.

## Adolescents / child (mid)

| Patient | CR_true | E0 | Gate | L −15 / +15 |
|---------|---------|-----|------|-------------|
| adolescent#001 | 1:21.5 | −0.17 | fail | — |
| adolescent#002 | 1:4.0 | +0.34 | fail | — |
| adolescent#003 | 1:21.5 | −0.42 | fail | — |
| adolescent#004 | 1:11.7 | −0.14 | pass | 0.53 / 0.15 |
| adolescent#005 | 1:12.0 | +0.35 | fail | — |
| child#001 | 1:40.0 | +0.30 | fail | — |

Younger cohort fails more often; one extra usable case, still not 0.7.

## Disturbances (adult#001, mid)

### Bolus timing

| Bolus vs meal | E0 | L −20 % | L +20 % |
|---------------|-----|---------|---------|
| −15 min | −0.07 | 0.27 | 0.24 |
| 0 | +0.04 | 0.19 | 0.30 |
| +15 min | +0.17 | 0.12 | 0.38 |
| +30 min | +0.35 (fail) | 0.02 | 0.49 |

Late bolus looks like a weak CR. 30 min late breaks phase 0.

### CGM gap (hold last reading from meal+20)

| Gap | E0 | L −20 % | L +20 % |
|-----|-----|---------|---------|
| 0 | +0.05 | 0.19 | 0.31 |
| 25 min | −0.71 | 0.58 | −0.19 |
| 40 min | −1.18 | 0.82 | −0.49 |
| 60 min | −1.50 | 0.92 | −0.75 |

A 25 min hole (the analysis tool’s own gap mark) already breaks phase 0
and can flip the sign when the CR is too weak.

Fat/protein is not in S2008 — not simulated.

## Not done (out of Phase A)

- Monte Carlo / full factorial (Phase B–C)
- Export through `loop_cr_review` (spec step 4)
- Second physiology model
- Changing `LOOP_RATIO`

## One-line result

A CGM-only loop *can* produce CR-dependent extra basal; it does not always,
and not at a fixed 70 % share. Treat `LOOP_SHARE = 0.7` as a generator
assumption only.
