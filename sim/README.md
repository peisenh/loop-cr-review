# sim/ — independent method-validation simulator

Implements [SIMULATION-SPEC.md](../SIMULATION-SPEC.md). Not part of the
analysis tool: no imports from `loop_cr_review`, dependency only in
`requirements-sim.txt`.

**Phase A is closed.** Findings: [UPTAKE.md](UPTAKE.md).

```bash
pip install -r requirements-sim.txt
PYTHONPATH=. python3 -m sim.check_plausibility   # open-loop physiology
PYTHONPATH=. python3 -m sim.cr_true              # measure CR_true
PYTHONPATH=. python3 -m sim.check_controller     # M1 isolation + E≈0
PYTHONPATH=. python3 -m sim.loop_uptake          # L vs CR error (mid)
PYTHONPATH=. python3 -m sim.phase_a              # gains × error grid
```
