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
