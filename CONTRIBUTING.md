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
3. Run the linter — the project targets a clean score:
   ```bash
   pylint loop_cr_review.py
   ```
4. Keep logic (`loop_cr_review.py`) and presentation (`templates/report.html.j2`) separate.
   Layout/wording changes belong in the template, not in Python.
5. Commit with `-s` (DCO sign-off) and open a Pull Request describing the change.

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
3. Linter laufen lassen — das Projekt zielt auf einen sauberen Score:
   ```bash
   pylint loop_cr_review.py
   ```
4. Logik (`loop_cr_review.py`) und Darstellung (`templates/report.html.j2`) getrennt halten.
   Layout/Wording gehört ins Template, nicht ins Python.
5. Mit `-s` committen (DCO-Sign-off) und Pull Request mit Beschreibung öffnen.

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
