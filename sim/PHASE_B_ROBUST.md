<!--
SPDX-FileCopyrightText: 2026 Peter Eisenhauer
SPDX-License-Identifier: CC-BY-SA-4.0
-->

# Phase B robustness — exit check

Not a new experiment. Freeze after this.

    PYTHONPATH=. python3 -m sim.robust_check --repro
    PYTHONPATH=. python3 -m sim.robust_check --seeds
    PYTHONPATH=. python3 -m sim.robust_check --boundary

## Pass (fixed now)

1. Same seed, two processes → identical stdout.
2. Seeds 1001/1002/1003 change the size of E, not the reading:
   0 % quiet; +30 % still has E vs D; +20 % may jitter.
3. Do not retune the analyzer, drop patients, or pick pretty seeds.

## Fail = also an exit

If (1) breaks, fix the seed path. If (2) flips the qualitative story,
write that the conclusion is sensitive and stop. Do not search for a
gain or patient that looks better.

## Result (2026-08-20)

Passed as an exit check. Same seed reproduces. Other seeds do not change
the reading. 0 % quiet. +30 % has E vs D at σ=0 and loses it at σ=5.
+20 % verdict jitters.

Simulation **frozen**. Analyzer unchanged.
