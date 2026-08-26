# VSCodium setup for loop-cr-review

The project uses the repository-local `.venv` for Python, debugging, tests and profiling.

## Install

```bash
cd ~/tools/loop-cr-review
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-web.txt
python -m pip install -r requirements-gui.txt
python -m pip install -r requirements-sim.txt
python -m pip install -r requirements-dev.txt

codium .
```

VSCodium selects `.venv/bin/python` automatically through `.vscode/settings.json`.

## Debug

Use **Run and Debug** and select:

- `CR Review – CLI`
- `CR Review – Web`
- `CR Review – GUI`
- `CR Review – Tests`
- `CR Review – Single Test`

The CLI profile starts against the repository's synthetic `example-data`.

## Tests

`Terminal → Run Task → Tests – unittest`

Equivalent command:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Profiling

Run:

1. `Terminal → Run Task → Profile – CLI`
2. `Terminal → Run Task → Profile – open SnakeViz`

This creates `profile.prof` in the repository root.

The profiling task deliberately uses the real CLI and `example-data`, so the result is comparable before/after code changes.
