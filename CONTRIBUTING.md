# Contributing / Mitwirken

Thanks for your interest in **loop-cr-review**! Contributions are welcome.
Danke für dein Interesse an **loop-cr-review**! Beiträge sind willkommen.

> ⚠️ **Reminder / Hinweis:** This is not a medical device and is for analysis only.
> Nothing here constitutes medical advice. — Dies ist kein Medizinprodukt und dient nur
> der Analyse; nichts davon ist eine medizinische Empfehlung.

---

## English

### Developer Certificate of Origin (DCO)

This project uses the **Developer Certificate of Origin**. By contributing, you certify the
statement below (DCO 1.1). Every commit must be **signed off**:

```bash
git commit -s -m "Your message"
```

This adds a trailer to the commit message:

```
Signed-off-by: Your Name <your.email@example.com>
```

Use your real name and a reachable email. Commits without a valid `Signed-off-by` line
cannot be merged. To sign off a range of existing commits, rebase with
`git rebase --signoff <base>`.

### Workflow

1. Fork the repository and create a topic branch.
2. Make your change; keep the diff focused.
3. Run the linter — the project targets a clean 10.00/10:
   ```bash
   pylint loop_cr_review.py webapp.py gui.py
   ```
4. Run the test suite; add cases for what you changed:
   ```bash
   python3 -m unittest discover -s tests
   ```
5. Keep logic (`loop_cr_review.py`) and presentation (`templates/report.html.j2`) separate.
   Layout/wording changes belong in the template, not in Python.
6. Commit with `-s` (DCO sign-off) and open a Pull Request describing the change.

Both checks also run in CI on every pull request, together with the Babel
catalog build.

### Scope & style

- Patient-specific content must stay **data-driven** — never hardcode names, values, or
  interpretations for a particular dataset.
- Clinical thresholds follow published consensus; method parameters live as named constants
  at the top of `loop_cr_review.py`.

---

## Deutsch

### Developer Certificate of Origin (DCO)

Dieses Projekt nutzt das **Developer Certificate of Origin**. Mit deinem Beitrag bestätigst du
die untenstehende Erklärung (DCO 1.1). Jeder Commit muss **signiert** werden:

```bash
git commit -s -m "Deine Nachricht"
```

Das fügt der Commit-Nachricht folgende Zeile hinzu:

```
Signed-off-by: Dein Name <deine.email@example.com>
```

Bitte echten Namen und erreichbare E-Mail verwenden. Commits ohne gültige `Signed-off-by`-Zeile
können nicht gemergt werden. Für bestehende Commits: `git rebase --signoff <basis>`.

### Ablauf

1. Repository forken, Topic-Branch anlegen.
2. Änderung umsetzen; Diff fokussiert halten.
3. Linter laufen lassen — das Projekt zielt auf saubere 10.00/10:
   ```bash
   pylint loop_cr_review.py webapp.py gui.py
   ```
4. Testsuite laufen lassen und Fälle für die Änderung ergänzen:
   ```bash
   python3 -m unittest discover -s tests
   ```
5. Logik (`loop_cr_review.py`) und Darstellung (`templates/report.html.j2`) getrennt halten.
   Layout/Wording gehört ins Template, nicht ins Python.
6. Mit `-s` committen (DCO-Sign-off) und Pull Request mit Beschreibung öffnen.

Beide Prüfungen laufen zusätzlich in der CI bei jedem Pull Request, zusammen
mit dem Bau der Babel-Kataloge.

### Umfang & Stil

- Patientenspezifisches bleibt **datengetrieben** — niemals Namen, Werte oder Interpretationen
  für einen konkreten Datensatz hartcodieren.
- Klinische Schwellen folgen dem publizierten Konsens; Methoden-Parameter stehen als benannte
  Konstanten oben in `loop_cr_review.py`.

---

## Developer Certificate of Origin 1.1

```
By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

Full text: <https://developercertificate.org/>

## Developer scripts

```bash
./tools/build-binaries.sh [cli|gui|webview2|all]   # PyInstaller build + checks
./tools/make-screenshots.sh               # regenerate docs/screenshot*.png
```

The build script mirrors the flags of the release workflow, bakes the version in
the same way and restores `_version.py` afterwards. Worth running before tagging:
a onefile binary can fail over a file that is not actually bundled or an import
PyInstaller does not follow, and the test suite never sees either. The CLI is
checked by generating a report from it; the GUI variants cannot be started
without a display, so their archive is read instead — for the templates, the
catalogs and, for the Qt variant, Qt itself.

Build the GUI from a virtual environment with the pip wheels:

```bash
python3 -m venv .venv-gui
source .venv-gui/bin/activate
pip install -r requirements-gui.txt pyinstaller
./tools/build-binaries.sh gui
```

Two things bite here, and the script checks both before building. PyInstaller has
to be installed *for the interpreter you build with* — a `pyinstaller` on the PATH
may belong to the system python and then bundles the system packages, which is why
everything runs through `python3 -m PyInstaller`. And the Qt runtime has to come
from the pip wheel, which carries `PyQt6/Qt6/libexec/QtWebEngineProcess` inside the
package; distribution packages split it across system paths, so `--collect-all
PyQt6` collects the bindings without the WebEngine helper and the binary aborts on
start with "base::CommandLine cannot be properly initialized".

Warnings about unresolved `libQt63D*` and `libQt6Quick3D*` libraries during the
build are expected — `--collect-all` also picks up QML plugins for modules that
are not installed. The CI build shows the same ones.

The screenshot script renders the report from `example-data` with whichever of
chromium/google-chrome is installed and writes both pictures into `docs/`. Look
at them before committing — a report that has grown past the captured height is
cut off without any error.

## Method validation

The unit tests pin the arithmetic; they do not validate the statistics. For that
there is a separate, reproducible script:

```bash
python3 tools/validate_bootstrap.py                  # coverage of the spread
python3 tools/validate_sensitivity.py                # what the rule can detect
PYTHONPATH=. pylint tools/validate_*.py
```

They measure, against a known truth, whether the "95 %" day spread really
covers it, whether decision stability separates clear from borderline slots,
and how large a carb-ratio error has to be before the rule notices it. The
committed results and their limits are in [VALIDATION.md](VALIDATION.md). The
next, not yet implemented step — an independent simulator to test the method's
core premise rather than its statistics — is specified in
[sim/SIMULATION-SPEC.md](sim/SIMULATION-SPEC.md). If you
change the gates, the bootstrap or the verdict rule, re-run it and update that
document.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The suite covers four areas:

- `test_analysis_core.py` — the method itself, with values computed by hand:
  loop extra basal over the window, `CR_eff`, the 4 h delta, contamination,
  consensus metrics and the verdict thresholds.
- `test_example_data.py` — parsers and the synthetic demo export end to end
  (its slot pattern is deliberately breakfast=strong, lunch=weak, dinner=ok).
- `test_webapp.py` — the web front-end: upload hardening, slot sources,
  options, reverse-proxy sub-paths.
- `test_gui.py` — the desktop launcher (backend selection, local server).
  Skipped automatically when the optional GUI dependencies are missing.

The web and GUI tests need their extra dependencies:

```bash
pip install -r requirements-web.txt -r requirements-gui.txt
```

When you change the analysis, add a case with a hand-computed expected value
rather than only asserting a direction — the whole point of these tests is to
catch a subtly wrong formula that still produces plausible-looking verdicts.
