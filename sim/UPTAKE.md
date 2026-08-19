# First empirical loop uptake (step 3, mid PID)

Not a LOOP_RATIO calibration. Controller is a CGM-only PID, not CamAPS.
CR_true is the Δ4h definition. Error +20 % = CR too weak.

## When L is even interpretable

At CR error 0 the extra basal must stay near zero. Otherwise the PID is
already driving the patient and L no longer measures meal shortfall.

Rule used here: |E| at 0 % ≲ 0.2 U on a 50 g meal (small vs. a ~1 U
shortfall at +20 %).

| Patient | CR_true | E at 0 % | L +20 % | L −20 % | L usable? |
|---------|---------|----------|---------|---------|-----------|
| adult#001 | 1:5.9 | +0.04 | 0.30 | 0.19 | yes |
| adult#002 | 1:7.6 | +0.09 | 0.49 | 0.32 | yes |
| adult#005 | 1:6.2 | +0.10 | 0.36 | 0.21 | yes |
| adult#003 | 1:11.7 | +0.37 | 1.07 | 0.17 | no (E0 already large) |
| adult#004 | 1:21.5 | +0.71 | 2.19 | −0.87 | no |
| adolescent#001 | 1:21.5 | −0.17 | 0.03 | 0.75 | no (almost no uptake when weak) |

On the three usable adults L at +20 % is 0.30–0.49, at −20 % 0.19–0.32.
Asymmetry matches the spec: less room to cut than to add.

## Step-3 decision

Outcome **B**: extra basal can track a shortfall, only for some virtual
patients and only with this mid PID. LOOP_SHARE = 0.7 stays a generator
assumption. Do not change LOOP_RATIO from this.
