# sim/ — independent method-validation simulator

Implements [SIMULATION-SPEC.md](../SIMULATION-SPEC.md). Not part of the
analysis tool: no imports from `loop_cr_review` except A.2 reading
`LOOP_RATIO`. Dependency only in `requirements-sim.txt`.

**Phase A is closed.** Findings: [UPTAKE.md](UPTAKE.md).

```bash
pip install -r requirements-sim.txt
PYTHONPATH=. python3 -m sim.check_plausibility   # open-loop physiology
PYTHONPATH=. python3 -m sim.cr_true              # measure CR_true
PYTHONPATH=. python3 -m sim.check_controller     # M1 isolation + E≈0
PYTHONPATH=. python3 -m sim.loop_uptake          # L vs CR error (mid)
PYTHONPATH=. python3 -m sim.phase_a --out sim/phase_a_results.csv
PYTHONPATH=. python3 -m sim.phase_a2 --in sim/phase_a_results.csv
PYTHONPATH=. python3 -m sim.phase_a3 --in sim/phase_a_results.csv
PYTHONPATH=. python3 -m sim.phase_a4 --in sim/phase_a_results.csv
PYTHONPATH=. python3 -m sim.phase_a5 --in sim/phase_a_results.csv
PYTHONPATH=. python3 -m sim.phase_a6 --in sim/phase_a_results.csv
PYTHONPATH=. python3 -m sim.phase_a7 --in sim/phase_a_results.csv
PYTHONPATH=. python3 -m sim.uptake_mech           # off-grid + hourly E
```

A.2–A.7 reuse the CSV. `uptake_mech` runs new short closed-loop traces.

End-to-end through the real readers:

```bash
PYTHONPATH=. python3 -c "
from pathlib import Path
from sim.export import run_days, write_export
write_export(run_days(days=5, cr_set=5.89), Path('/tmp/exp'))
"
python3 loop_cr_review.py /tmp/exp -o /tmp/exp.html
```
