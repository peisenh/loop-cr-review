# sim/ — independent method-validation simulator

Implements [SIMULATION-SPEC.md](../SIMULATION-SPEC.md). Not part of the
analysis tool: no imports from `loop_cr_review`, extra dependency in
`requirements-sim.txt` only.

Current step: **physiology without a controller** (spec §13.1).

```bash
pip install -r requirements-sim.txt
python3 -m sim.check_plausibility
```

```bash
python3 -m sim.cr_true
```

`CR_true` is measured, not set (spec §5). Two definitions (Δ4h ≈ 0 vs. min area);
a large gap between them is a result, not something to average away.

```bash
python3 -m sim.check_controller
```

```bash
python3 -m sim.loop_uptake
```

First L numbers: [UPTAKE.md](UPTAKE.md).

```bash
python3 -m sim.phase_a
```
