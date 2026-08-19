# Empirical loop uptake — status

The simulation is no longer circular. **Outcome B is not locked.**

## Phase 0

|E| at zero CR error ≲ 0.2 U (50 g, mid PID) before L is read.

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

Five of ten pass. On those, L stays between about 0.2 and 0.55, both
signs, no 0.7. #007 shows a high CR_true can still pass; extreme CR_true
is not the gate by itself.

Gains (first slice, #001/#002/#005): only #002 stays in gate for
weak/mid/strong; then L is almost gain-independent.

## 5 / 10 / 25 % on the five passers (mid)

L at ±5 % jumps (0.04–0.68): the shortfall is tiny, so E/D is noisy.
From about ±10 % it settles in the same 0.2–0.55 band as before.

#007 is flat in L (~0.5) but Δ4h stays around −23 mg/dl at every error —
E-gate alone does not make the glucose story healthy.

Still missing: adolescents/children, disturbances.
