<!--
SPDX-FileCopyrightText: 2026 Peter Eisenhauer
SPDX-License-Identifier: CC-BY-SA-4.0
-->

# Specification: an independent simulator to test the loop-CR method hypothesis

Status: **code for steps 1–3 exists** under `sim/`. Formal Phase A adult grid is specified in `sim/phase_a.py` and summarised
in [sim/UPTAKE.md](sim/UPTAKE.md). Phase B first slice + exit check: [PHASE_B_DESIGN.md](PHASE_B_DESIGN.md), [PHASE_B_ROBUST.md](PHASE_B_ROBUST.md). Simulation frozen.
Companion to [VALIDATION.md](VALIDATION.md).

---

## 0. Hard requirements

Fixed before the first line of code, because each one is expensive to retrofit:

* **M1 — information isolation.** The controller may see the CGM value and
  nothing else: no `meal`, no carb amount, no carb ratio, no bolus, no patient
  state. **Checked against the code:** simglucose passes both `meal=CHO` and
  `patient_state` to *every* controller in `T1DSimEnv.step`, and the shipped
  `BBController.policy` reads `meal` from kwargs and knows the carb ratio and
  correction factor. It is unusable for this purpose. Isolation therefore does
  not happen by itself; it has to be enforced in our own controller — and
  **tested**: a test alters `meal`/`patient_state` and asserts the controller
  output does not change. Single exception, read once at setup: the patient's
  basal profile (a pump setting, §4).
* **M2 — the three CR quantities are defined before the first run** (§5).
* **M3 — the primary endpoint is the empirical loop uptake**, not the verdict
  table (§7.1). First: how much extra basal arises at all? Only then: what does
  loop-CR make of it?
* **M4 — understand parameters before randomising them.** One factor at a time,
  then factorial, then Monte Carlo (§6).

## 1. Why at all

The existing validation (`VALIDATION.md`) answers two questions:

* does the bootstrap behave the way its label claims (coverage), and
* how large must an error be before the rule reacts (sensitivity).

Both use a generator that **prescribes the loop extra basal**: it assumes the
controller absorbs a fixed share (`LOOP_SHARE = 0.7`) of a meal's insulin
shortfall as additional basal. That tests the formula against its own premise.
Acceptable for the statistical questions, not for the methodological one:

> Does `CR_eff = CHO / (bolus + loop extra basal)` actually measure the carb
> ratio the body needed — or only the assumption we put in?

It becomes non-circular only when the extra basal **emerges from a control
loop** that does not know the meal size and reacts solely to the simulated
glucose trace.

## 2. Architecture

```
              CR_ref (measured)
                    │
CR_set ─→ bolus ─→ physiology ─→ CGM
                                  │
                                  ▼
                          CGM-only controller
                                  │
                                  ▼
                     basal profile ± Δbasal
                                  │
                   ┌──────────────┴──────────────┐
                   ▼                             ▼
             loop uptake L                    CR_eff
                   │                             │
                   └──────────────┬──────────────┘
                                  ▼
                          method assessment
```

The export takes the detour through the real readers:

```
simulation → Glooko-style CSV → existing readers → existing analysis → report
```

Not through a special-purpose data structure: otherwise we would eventually be
validating a second analysis built for the simulation. The export is therefore
also an integration test of the whole data path, including the fasting-basal
logic.

**Strict separation:** own directory (`sim/`), no imports from the analysis path
into the simulation.

## 3. Physiological model — candidates

**Bergman alone is not enough.** The minimal model comes from the intravenous
glucose tolerance test, without a meal and with heavily simplified insulin
kinetics. But the insulin action curve is exactly what matters here: it governs
how much of a shortfall a controller can still make up inside the 4 h window. A
model too coarse in that respect would decide the outcome in advance.

### A) simglucose (UVa/Padova S2008) — **recommended as the primary model**

Python implementation of the FDA-accepted UVa/Padova simulator (2008 version),
MIT-licensed, with 30 virtual patients (10 adolescents, 10 adults, 10 children),
a gym-style interface, a shipped PID controller and free meal scenarios.
<https://github.com/jxx123/simglucose>

* **For:** we do not write our own physiology — that is the whole point of the
  exercise. Externally developed, published model with a defined virtual cohort;
  the argument is provenance, not popularity. Patient variability is built in
  rather than invented by us. The controller interface *allows* the required
  isolation (own controller, returns basal/bolus) but does not guarantee it —
  see M1.
* **Against, and this one matters for us:** for S2008 the incidence of
  hypoglycaemia was found not to match clinical trials; S2013 first added an
  insulin-dependent compartment that improves glucose kinetics in the hypo
  range. That range is precisely where our **asymmetry hypothesis** (§7.4)
  lives. S2013/S2017 are not freely available.
  → Consequence: the "carb ratio too strong" branch is only partly trustworthy
  with S2008 and must be labelled as such in the results.
* **Licence: clear.** The `LICENSE` file is plain MIT with no extra clause; the
  README's "for research purpose only" is prose, not a term (details in §10).
* **Dependencies:** pulls in scipy/pandas among others. Development tool only
  (simulation in `sim/`, evaluation script in `tools/`), **never** in the
  analysis tool's `requirements.txt`.

### B) Hovorka model (own implementation)

The model of the Cambridge group around Roman Hovorka — the same lineage as the
algorithm in CamAPS FX, the real system behind our data.

* **For:** closest relation to the actual control loop; equations published;
  three insulin compartments and a carbohydrate absorption model are part of it.
* **Against:** an own implementation means own bugs — and it weakens the very
  argument we are after, independence. Parameters would have to be sourced from
  the literature and given ranges.
* **Verdict:** worthwhile as a *second* model for cross-checking, not as the
  first.

### C) Own minimal model (Bergman + absorption + 3-compartment insulin)

* **For:** small, dependency-free, fully controllable, ranges freely chosen.
* **Against:** the weakest external credibility; we would be choosing the
  physiology we validate against.
* **Verdict:** fallback if A is ruled out on licence or dependency grounds.

### Recommendation

**A as the primary model, C as a cross-check.** Two models are not a luxury
here: if both agree on the empirical loop uptake (§7.1), the result is far more
robust than from one. If they disagree, **that is the result** — and the honest
consequence would be to derive no recalibration of `LOOP_RATIO` from it.

Parameters are not point values in either case: in A through the virtual cohort,
in C through documented ranges. What gets reported is the spread of outcomes,
not a single number.

## 4. Controller

A controller that modulates the basal rate from the glucose error:

* Input: simulated CGM only (noise, the sensor's native 3-minute grid;
  resampling to 5 minutes happens for the *export*, §6).
* Output: temporary basal rate, clamped to `[0, k × basal profile]`.
* No meal knowledge, no bolus advice, no multi-day adaptation.

simglucose ships a PID controller. **Checked against the code:** it really does
use only `observation.CGM` (plus `sample_time`) and satisfies the "glucose only"
condition out of the box. The meal bolus comes separately from the simulated
user side (from the deliberately mis-set carb ratio).

**But it is not usable unmodified** — two findings from the code:

* It returns `basal = P·(bg − target) + …` as an **absolute** value, not as an
  offset on a basal profile. With glucose at target the basal rate would be near
  zero and the patient would drift high overnight. More importantly, our tool
  would have no meaningful **fasting basal rate** as a reference — the very
  quantity `loop extra basal` is built on.
  → Required: `basal = basal profile + PID offset`, clamped to
  `[0, k × basal profile]`.
* The basal profile itself is derivable from the patient parameters
  (`u2ss × BW / 6000` U/min; about 1.27 U/h for `adult#001`). That is **not** an
  information leak: a basal rate is a legitimate pump setting. It is read **once
  at setup**, never per step from `patient_state` — otherwise M1 is violated.

**Known dissimilarity to CamAPS.** CamAPS FX uses the adaptive Cambridge MPC: it
computes the insulin rate every 8–12 minutes, is initialised from body weight
and total daily dose, and **adapts its dosing to glucose patterns over days and
weeks**; default target 5.8 mmol/L (105 mg/dL). The PID differs structurally
from that. The direction and size of its influence on the loop uptake are
**not assumed in advance** but investigated by varying controller aggressiveness.

Consequences for the setup:

1. **Controller aggressiveness as a parameter** across a range (weak / medium /
   strong). Result statement accordingly: "the detection threshold lies between
   X and Y % carb-ratio error depending on controller strength" — not a single
   number.
2. **Adaptation deliberately omitted** and declared as a limit. Multi-day
   adaptation is one of the confounders the report itself names; simulating it
   without knowing the real algorithm would fake precision.
3. **No reimplementation of a commercial algorithm.** The goal is a generic
   control loop, not CamAPS.

## 5. The three CR quantities — and how the reference is determined

Without this separation one silently treats the setting as the truth.

| Quantity | Meaning |
|---|---|
| `CR_set` | the deliberately (mis-)configured ratio the bolus is computed from |
| `CR_ref` | the reference ratio, **measured** in the simulated body, not set; two variants `CR_ref_Δ4h` and `CR_ref_AUC` |
| `CR_eff` | what loop-CR reconstructs: `CHO / (bolus + loop extra basal)` |

**`CR_ref` is measured, not stipulated.** Deliberately not called "CR_true": it
is the reference *of this model under these conditions*, not a physiological
truth. It is determined **separately per patient, meal type and absorption
configuration** — otherwise we would compare the reference bolus of a fast meal
against a fat/protein meal.

Procedure, run separately from the actual experiment:

1. Controller off, basal held at the patient's basal profile
   (`u2ss × BW / 6000`, §4) — open loop.
2. Titrate the bolus for one meal until glucose is back at its starting value
   after the window (Δ4h ≈ 0). The bolus `B*` found this way defines
   `CR_ref_Δ4h = CHO / B*`.
3. Determined once per patient and kinetics variant, then held constant.

**Known weakness of this definition:** it adopts the tool's own success
criterion (return to baseline after four hours). A bolus that drives Δ4h to zero
may have produced a spike or a hypo in between. As a cross-check a second
definition is carried along — `CR_ref_AUC`, minimising the area between the
glucose trace and target across the window — and it is reported whether both
lead to a similar reference. If they do not, then even the question "what is the
correct carb ratio" is worse posed than assumed, and that belongs in the result.

## 6. Experimental plan — in phases

Not Monte Carlo straight away: otherwise a wide cloud comes out at the end
without any idea why it is wide. Order: **phase 0 → A → B → C**.

**Phase 0 — null model.** `CR_set = CR_ref`, i.e. a correct bolus, controller
active, several days, no deliberate disturbances. Measured: the natural positive
and negative basal deviation, the spread of `CR_eff`, and the method's false
alarm rate.

This is not a warm-up but the baseline: the controller reacts to glucose
fluctuations even with a perfectly set ratio, so apparent extra basal arises
without any carb-ratio error at all. Without this baseline we could not later
claim that the uptake at +10 % is a CR signal — it could be noise. If the
apparent loop uptake is already substantial here, that is a result in itself.

**Phase A — one parameter at a time.** Everything else constant, varying only
absorption, insulin kinetics, controller strength or carb-ratio error. Goal:
make causality visible.

**Phase B — factorial.** Absorption (fast/medium/slow) × insulin action
(fast/medium/slow) × controller (weak/medium/strong). Goal: reveal interactions.

**Phase C — Monte Carlo.** Only now random draws from the virtual cohort and the
parameter ranges, for the summary statements.

Across all phases:

| Factor | Values |
|---|---|
| carb-ratio error | −30, −25, −20, −15, −10, −5, 0, +5, +10, +15, +20, +25, +30 % |
| days | 7, 14, 21 |
| controller strength | weak, medium, strong |
| disturbances | fat/protein meals, CGM gaps, bolus timing errors |

**Error convention, spelled out because it is easy to invert:**

```
CR_set = CR_ref × (1 + err)
err > 0  →  CR_set larger   →  less insulin per gram  →  bolus too small (too weak)
err < 0  →  CR_set smaller  →  more insulin per gram  →  bolus too large (too strong)
```

So the **setting** is varied, not the reference: `CR_ref` is a measured property
of the virtual patient and stays fixed.

The points at ±5 and ±10 % are needed to locate the detection threshold at all —
the current analysis puts it around 15 %, and a grid that starts there could not
resolve it. Symmetric, because the asymmetry hypothesis (§7.4) would otherwise
not be testable.

**Technical note, checked against the code:** the Dexcom sensor in simglucose
produces a value every **3 minutes**, real Glooko exports every 5. The export
must therefore be resampled onto a 5-minute grid — otherwise we would test the
tool at a data density that never occurs in practice, and gap detection
(>25 min) would behave differently than in production.

## 7. What gets measured

Not just "is the verdict right", but above all:

1. **Empirical loop uptake** `L`. What share of the shortfall actually shows up
   as extra basal? Operationally:

   ```
   shortfall   D = CHO/CR_ref − CHO/CR_set        (CR_ref measured, §5)
   extra basal E = ∫ (basal rate − basal profile) dt   over the 4 h window
   loop uptake L = E / D                          (for D ≠ 0)
   ```

   `L` stays positive in **both** directions (with over-dosing `D` and `E` are
   both negative), so it is comparable. It is nevertheless reported **separately
   for `err > 0` and `err < 0`** — not because of the sign, but because of
   saturation: downwards `E` is bounded by the basal profile
   (`|E| ≤ basal profile × window`), upwards it is not. Under strong over-dosing
   `L` must therefore fall, and a value averaged across both directions would
   hide exactly the effect §7.4 is meant to test.

   `L` is determined per meal and reported as a distribution across patients,
   kinetics and controller strengths — not as a single value. This is the
   currently guessed constant `LOOP_SHARE = 0.7`. If something clearly different
   comes out, the consequence is not merely "validated / not validated" but a
   possible **recalibration of `LOOP_RATIO`** — the actual practical payoff.
2. **Does `CR_eff` hit the reference ratio?** Systematic offset (bias) and
   spread, plotted against the size of the carb-ratio error.
3. **Detection performance** analogous to the existing table, but without a
   prescribed extra basal — directly comparable to `VALIDATION.md`.
4. **Asymmetry hypothesis.** Prediction: with a ratio that is too weak the
   controller can add arbitrarily much extra basal; with one that is too strong
   it can at most throttle down to zero. Beyond a certain degree of over-dosing
   the **signal saturates**, and the remainder shows up as hypoglycaemia instead
   of negative extra basal. The current linear sensitivity analysis cannot see
   this in principle. If it holds, it belongs in the report's method box — it
   would mean "too strong" is detected worse than "too weak".

   **Pre-registered, not read in afterwards:** the evaluation is built so that it
   *can* refute the hypothesis — separate detection rates for positive and
   negative errors, no single figure mixing both directions. If it is not
   confirmed, that is reported just as plainly.

## 8. Result format

The tables for §7.1–§7.4 plus a short text as a third section in
`VALIDATION.md`, produced by a script in `tools/`, with a fixed seed and a
documented invocation — like the two existing validations.

## 9. Limits — what this setup also cannot show

* **A simulator is itself a model.** If its insulin kinetics or absorption are
  off, one validates against the wrong truth. The parameter ranges (§3) damp
  that; they do not remove it.
* **The controller is not CamAPS.** No MPC, no meal announcement, no multi-day
  adaptation. The last of these is one of the confounders the report names, and
  it stays unsimulated.
* **No clinical proof.** The result would be "simulation supports the method
  under model assumptions" — not "loop-CR is validated". Definitive evidence
  would need real data with documented carb-ratio changes and the course that
  followed.
* **No statement about individual cases.** All numbers are distributional
  statements across many simulated weeks.

## 10. Dependency and licence

* **Licence, resolved.** The repository's `LICENSE` is an unmodified MIT licence
  (Copyright (c) 2017 Jinyu Xie) with no additional clause; the package metadata
  states `License: MIT`. The phrase "for research purpose only" appears only in
  the README prose, not in the licence, and reads as two caveats rather than
  terms: the implementation follows the 2008 model version, and it is not meant
  for clinical use. Neither conflicts with our purpose. MIT is also compatible
  with this project's AGPL — and the question barely arises, since simglucose is
  not redistributed here but used as an optional development dependency.
  (This is a reading of the files, not legal advice; if certainty matters, one
  question to the author via a GitHub issue settles it.)
* **Attribution.** MIT requires the copyright notice only on redistribution, but
  the author explicitly asks to be cited. The citation belongs in `VALIDATION.md`
  next to the results, together with the model references the parameter
  definitions are derived from (Dalla Man et al., meal simulation model; UVA/
  PADOVA T1D simulator, new features).
* **Pin the version**, record commit/tag in the result document — otherwise the
  numbers are not reproducible.
* Carry or reference the licence text.
* **Development dependency only**, never in the analysis tool's
  `requirements.txt`.
* Before the actual validation, an own plausibility test set: a meal without
  bolus rises, a bolus by `CR_ref` returns to baseline, the night stays flat.
  Only once that holds does any result above it mean anything.

## 11. Possible outcomes

Three outcomes, and all three are results:

* **A — supports the method.** Extra basal arises independently and `CR_eff`
  tracks `CR_ref` robustly across models, kinetics and controller strengths.
* **B — constrains it.** It only holds within certain kinetics or controller
  ranges. The consequence would be stated conditions in the report under which
  the statement applies.
* **C — refutes a core assumption.** Physiologically arising extra basal does
  not correlate sufficiently with the carb-ratio error. That would be **no
  failure of the project** but the most valuable possible finding: the
  interpretation of extra basal — and with it `LOOP_RATIO` — would need a
  fundamental rework.

## 12. Non-goals

* No replacement for the existing unit tests or the statistical validation.
* No extension of the tool itself; the simulation stays an analysis instrument
  in the repository, not part of the report pipeline.
* No reimplementation of any specific commercial algorithm.

## 13. Implementation order

1. Physiology + absorption, no controller: check that a bolus by the configured
   ratio produces a plausible curve (peak, return to baseline).
2. Add the controller, no carb-ratio error: check that it holds the target range
   and that extra basal fluctuates around zero.
3. Introduce the carb-ratio error, measure the empirical loop uptake (§7.1) —
   **this is where it is decided whether the core assumption holds.**
4. Write the export, run it through `loop_cr_review`, produce the detection
   tables.
5. Sweep parameter and controller ranges, report the spreads.

Step 3 is the point at which the project can fail or convince. If the measured
loop uptake deviates strongly from 0.7 or scatters very widely, that is a result
in itself — and more important than any detection table below it.

**Stopping rule, fixed in advance:** if phase 0/A shows that `L` is not roughly
stably related to the shortfall, the work ends there and the result is reported
as such. It would be methodologically unsound to then go looking for a positive
result in the verdict table instead.
