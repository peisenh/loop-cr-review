<!--
SPDX-FileCopyrightText: 2026 Peter Eisenhauer
SPDX-License-Identifier: CC-BY-SA-4.0
-->

# Bootstrap validation

Where the numbers behind the day spread and the decision stability come from,
and where they stop being trustworthy. Reproduce with:

```bash
python3 tools/validate_bootstrap.py --reps 800 --boot 500 --seed 20260819
```

The table below is one such run (a few minutes). The default invocation is much
quicker and good enough to see the shape.

## What is being validated

Synthetic slots are drawn with a **known** median CR_eff (8.0) and a known loop
share, then run through the same `decision_stability()` the report uses. Two
questions:

1. Does a spread labelled "95 %" actually contain the true median about 95 % of
   the time?
2. Does the stability figure separate a clear-cut slot from one sitting exactly
   on the threshold?

## Coverage of the 95 % spread

| days | below gate | coverage | mean width |
|-----:|:-----------|---------:|-----------:|
| 3 | yes | 74.9 % | 2.50 |
| 4 | yes | 88.4 % | 3.07 |
| 5 | no | 93.9 % | 3.54 |
| 6 | no | 92.9 % | 2.78 |
| 8 | no | 89.2 % | 2.25 |
| 10 | no | 93.5 % | 2.26 |
| 14 | no | 93.5 % | 1.83 |
| 20 | no | 94.0 % | 1.57 |

**Reading it.** Below five days the label is plainly wrong — at three days a
"95 %" spread holds three times out of four. That is why the gate sits at five
days and why thinner slots fall back to the plainly observed range instead.

From five days upward the spread lands in the low nineties rather than at a
clean 95 %, and the sequence is **not monotone** (the eight-day cell is lower
than six and ten). Percentile bootstrap intervals for a *median* are known to be
irregular at small sample sizes, and the remaining wobble is sampling noise of
this validation itself. So: treat the label as "about 90–95 %", not as an exact
guarantee.

## Decision stability

| case | mean stability | reported "high" |
|:-----|---------------:|----------------:|
| clear (loop share 3× threshold) | 100 % | 100 % |
| moderate (1.5× threshold) | 83 % | 43 % |
| borderline (exactly at threshold) | 76 % | 19 % |

**Reading it.** The figure does what it is meant to do: an unambiguous slot is
reported as fully stable, a borderline one is not. But note the last row — even
a slot sitting exactly on the threshold is called "high" in roughly one run in
five. A high stability is therefore evidence, not proof; it does not rule out
that the slot is a coin flip.

## What this does *not* show

The generator draws independent days with clean, well-behaved meals. Real
exports violate every one of those assumptions: loop adaptation over days,
fat/protein tails, corrections mixed into a bolus, movement, pre-bolus timing,
drifting basal need, CGM gaps. None of that is simulated here.

These numbers therefore validate the **resampling procedure**, i.e. that the
estimator behaves as advertised on data that matches its assumptions. They are
an upper bound. They say nothing about whether the carb-ratio inference itself
is correct on real data — that would need either a physiological simulator that
does not share this tool's assumptions, or clinical reference data.

## Sensitivity: what the rule can actually see

Reproduce with:

```bash
python3 tools/validate_sensitivity.py --reps 1500 --markdown
```

Slots are generated from a **known** carb-ratio error, then run through the real
verdict rule. The table gives how often a slot is called "too weak" (and, in the
first row, how often a correctly set slot is correctly left at "ok").

| true CR error | 5 days | 7 days | 10 days | 14 days | 21 days |
|---:|---:|---:|---:|---:|---:|
| 0 % (correct) | 66 % | 76 % | 87 % | 94 % | 97 % |
| 5 % | 27 % | 20 % | 13 % | 11 % | 6 % |
| 10 % | 39 % | 34 % | 32 % | 27 % | 23 % |
| 15 % | 55 % | 57 % | 54 % | 55 % | 54 % |
| 20 % | 73 % | 77 % | 81 % | 81 % | 86 % |
| 25 % | 89 % | 91 % | 96 % | 97 % | 98 % |
| 30 % | 97 % | 98 % | 100 % | 100 % | 100 % |

**Reading it.** The rule crosses the 50/50 mark at roughly a **15 % carb-ratio
error** — that follows directly from the 0.12 loop-share threshold and the
assumption that the loop absorbs about 70 % of a meal's shortfall. It becomes
reliable (>90 %) only from about **25 %**. A 10 % error is below what the method
is built to react to, and firing there would not be desirable anyway.

The more uncomfortable column is the first one: with only **five days a
correctly set slot is still flagged in a third of runs**. Days help far more
against false alarms than they help detection — detection at a 20 % error rises
only from 73 % to 86 % between 5 and 21 days, while the false-alarm rate on a
correct slot falls from 34 % to 3 %. That is the strongest argument for
collecting a couple of weeks before acting on a verdict.

### Robustness (20 % error, 10 days)

| disturbance | detected | false alarm |
|:---|---:|---:|
| clean | 81 % | 14 % |
| 20 % outlier days | 78 % | 22 % |
| 20 % CGM gaps | 78 % | 13 % |
| 10 % bolus noise | 78 % | 13 % |
| all three | 76 % | 26 % |

Outliers, CGM gaps and bolus noise barely move detection; what they do is raise
false alarms (14 % → 26 % with all three). Noise makes the method **more likely
to cry wolf**, not more likely to miss a real error.

### Threshold sensitivity

| threshold | value | detected | false alarm |
|:---|---:|---:|---:|
| -10 % | 0.108 | 83 % | 17 % |
| as shipped | 0.120 | 78 % | 12 % |
| +10 % | 0.132 | 73 % | 11 % |

Moving `LOOP_RATIO` by ±10 % shifts detection and false alarms by only a few
points — the rule is not balanced on a knife edge with respect to that constant.

### Limits of this section

The generator uses the tool's own premise: the loop extra basal covers a fixed
share of the meal's shortfall, days are independent, and only the listed
disturbances occur. Noise levels are calibrated against real exports (day-to-day
sd of the loop extra 1.1–3.7 U, of the 4 h delta 27–78 mg/dL), but adaptation
over days, fat/protein tails, corrections blended into a bolus and exercise are
**not** simulated. These are therefore best-case detection rates.

