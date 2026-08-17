# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).
Entries up to and including 0.5.3 are in German; newer entries are in English.

> Not a medical device — analysis only. No diagnosis, no treatment recommendation.

## [Unreleased]
### Added
- Desktop launcher tests (`tests/test_gui.py`, 12 cases): pywebview backend
  selection per platform/build including the `LOOP_CR_GUI` override, the
  local-port helpers, and that the bundled waitress server serves the same
  Flask app on loopback only.
- Dependabot config for pip, GitHub Actions and Docker (weekly, grouped
  minor/patch bumps). The DCO workflows now skip bot commits, which cannot
  carry a Signed-off-by line.
- Web front-end regression tests (`tests/test_webapp.py`, 25 cases): upload
  hardening (zip-slip, absolute paths, decompression bombs, entry floods,
  corrupt archives), the three slot sources (built-in / field editor / uploaded
  JSON) including the two bugs fixed below, option validation, the download
  switch and reverse-proxy sub-path awareness. Malformed input is asserted to
  return HTTP 400 rather than 500. CI now discovers all test modules and
  installs Flask so the web suite runs on every push.

### Changed
- Upload form: Babel i18n (de/en), switchable via language field; default remains German.
- CI: align checkout/setup-python with build-release (v7; Node 20 deprecation warning).
- All internal error and status messages are now consistently English, matching
  the rest of the code base (argparse help, web-layer aborts, docstrings). The
  `LoopCRError` texts and the CLI's success line were the last German holdouts.
  User-facing output (report, upload form) stays fully localised via gettext.
- Code quality back to pylint 10.00/10: explicit exception chaining in
  `load_slots_file`, public `current_translation()` accessor instead of reaching
  into the core's private ContextVar from the web layer, `importlib.util.find_spec`
  instead of a throwaway import when probing for PyQt6, and `.pylintrc` limits
  raised with a rationale for the data-assembly functions and the dark-mode charts.

### Fixed
- Report: the `<html lang>` attribute now follows the selected report language
  instead of being hardcoded to `de` (content was already translated correctly;
  this only affected screen readers and browser language detection).
- Web front-end: invalid slots entered in the field editor returned HTTP 500
  instead of 400 — that path still caught only the legacy `SystemExit` and not
  `LoopCRError`. The uploaded-JSON path was already correct.
- Web front-end: the automatically appended catch-all slot used a hardcoded
  label, so a German report showed the English "Other" for field-editor slots.
  It now uses the same msgid as the built-in slot and is translated normally.

## [0.8.3] - 2026-08-17
### Changed
- Windows desktop: slim WebView2 build (`loop-cr-review-gui-windows.exe`) plus full Qt
  build (`…-gui-windows-qt.exe`); Linux GUI stays Qt.


## [0.8.2] - 2026-08-17
### Changed
- Dark mode: upload UI and report follow `prefers-color-scheme`; report print stays light;
  charts embed light+dark PNGs in the same HTML file.
- Clean-meal selection: exclude meals with a CGM gap > 25 min in the post-meal
  window when at least 3 gap-free clean meals exist (fallback: all meals).
- README (de/en) and web upload: short privacy / homelab notes (self-hosted only, no public hosting).
- Unittest + Babel workflow on every push/PR (.github and .gitea, mirrored).
- Report limitations: note that CamAPS Boost/Ease-off are not in the Glooko CSV export and can
  distort CR signals when active (manual awareness only).
- Analysis state (slots, language, glucose unit) uses ContextVars so concurrent
  web/GUI requests do not leak configuration across threads.


## [0.8.1] - 2026-08-16
### Changed
- Report presentation: clearer CR column headers —
  ``CR (CHO/bolus)`` vs ``CR_eff (+loop)`` — and an explicit note that both are
  derived from the export, not the pump’s programmed ICR.
- Short method box near the top of the HTML report (CamAPS scope, loop
  extra-basal formula, two ratios, discussion-only use).
- Absolute postprandial curve: short note that it uses all meals per slot, while the CR table and baseline-normalised curves use the clean-meal rule (so n/shape may differ by design).
- Interpretation legend tags aligned with table verdict wording (too strong → loosen / too weak → tighten / plausibly adequate).
- Low-confidence slots: clearer hatching, dashed outline, and a “low confidence” tag in the CR table and derivation cards; legend notes the hatched row.
- Web upload UI: explicit CamAPS FX (Auto Mode) only notice; README lead-in points to the supported-systems section.


## [0.8.0] - 2026-08-16
### Added
- Desktop app (`gui.py`): runs the web front-end in a native window via
  pywebview + Qt (PyQt6 WebEngine), backed by a local waitress server —
  a double-click binary with no browser, no Docker, localhost only.
  Pre-built binaries for Windows and Linux are built in CI and attached
  to releases; `requirements-gui.txt` covers a run from source.
  Reuses the same templates, reports and analysis as the CLI/web.
  Note: binaries are larger (\~250–280 MB) because the Qt WebEngine is bundled.
- `example-data/Alex_Beispiel_Glooko_export.zip`: Glooko-style ZIP of the
  synthetic demo export (CSV files only) so the web front-end upload path
  can be tested without packaging the folder by hand.
- Automated regression tests (`tests/test_example_data.py`) against the
  synthetic example export: parsers, slot JSON, demo slot verdicts
  (breakfast strong / lunch weak / dinner ok), English report, and ZIP
  extract ≡ folder analysis. Run with `python3 -m unittest tests.test_example_data -v`.

### Changed
- Analysis core raises :class:`LoopCRError` instead of calling ``sys.exit``
  for invalid slots, unreadable slot files and missing basal data; the CLI
  maps that to exit code 1 and the web front-end to HTTP 400.
- ``generate_report`` installs custom slots only inside a scoped context
  (``_slot_scope``) and restores the built-in ``DEFAULT_SLOTS`` afterwards,
  so concurrent GUI/web requests do not leak slot configuration via module
  globals.
- ``select_slot_rows()`` is the single rule for which meals feed a slot's
  median table/verdict and the baseline-normalised curves (prefer
  contamination-free rows, fall back to all if fewer than
  ``MIN_CLEAN_MEALS``). Behaviour unchanged; absolute median curves still
  use every meal in the slot by design.

## [0.7.0] - 2026-08-15
### Added
- Optional homelab web front-end (`webapp.py`, Flask): upload a CamAPS/Glooko
  export ZIP, pick language/window/daily and the time-of-day slots, get the HTML
  report back. Slots can be left at the built-in default, entered as fields
  (label/start/end, catch-all added automatically) or uploaded as JSON; an
  optional switch downloads the report instead of showing it. Health data is
  processed in a temporary directory and deleted immediately (ephemeral, nothing
  stored). Intended for private LAN use, not public hosting. Ships with a
  `Dockerfile`, `docker-compose.example.yml` (with an optional, commented-out
  Traefik reverse-proxy block) and `requirements-web.txt`; run behind gunicorn.
  Not installed or imported by the CLI.
- The web front-end is reverse-proxy aware: it honours X-Forwarded-Prefix/Proto/
  Host, so it can run under a sub-path (e.g. /loop-cr-review behind Traefik
  StripPrefix) with correct links and HTTPS redirects. Form and asset URLs use
  url_for so they inherit the prefix.
- Reusable `generate_report()` entry point in `loop_cr_review.py` that returns the
  HTML (and context) without writing files or printing, so front-ends other than
  the CLI can drive the same analysis. The CLI is now a thin wrapper around it.
- Shared `build_slots()` validation used by both the slots JSON file and the web
  field editor, so a single set of rules governs custom slots everywhere.
- Project logo embedded inline at the top of the HTML report (still a single
  self-contained file); the version is now shown in both the report header and
  the web front-end, baked from `git describe` during the Docker build.

### Changed
- The daily graphs are now ordered oldest-first, matching the per-meal detail
  table, so the whole report reads chronologically top to bottom and a meal in the
  table lines up with its day in the graphs. Previously the daily graphs were
  newest-first while the table was oldest-first.

### Fixed
- No more "No artists with labels found to put in legend" warning when an export
  contains no meals (e.g. only overnight data). The slot-curve charts now draw a
  legend only when there is at least one labelled curve. The report itself was
  always produced correctly; this only silences the cosmetic matplotlib warning.
- Hardened the parsing of untrusted input files so malformed data fails with a
  clear message instead of a raw traceback. A custom slots file now rejects
  entries that are not objects and start/end values that are not whole numbers.
  The CSV readers for meals, bolus events and the basal timeline skip rows that
  are too short instead of raising IndexError, and an empty basal timeline aborts
  with a clear message. Non-finite numbers (inf/-inf) are now read as nan like
  empty cells, so a manipulated value can no longer poison a mean or crash the
  basal duration. Autoescaping already prevented HTML in slot labels from
  reaching the report unescaped; no change was needed there.

### Security
- Web front-end: hardened ZIP upload handling. Extraction now caps the number of
  entries and the per-file and total uncompressed size to stop decompression
  bombs, in addition to the existing zip-slip/absolute-path rejection. Any failure
  while building a report from a malformed export is turned into a clean HTTP 400
  instead of a 500 with a traceback.

## [0.6.3] - 2026-08-12
### Fixed
- Hypo rescues in an otherwise adequate slot are now handled in three tiers by
  what share of the slot's meals needed a rescue, so the verdict and the levers
  always agree. No rescue → "dose fits — leave as is" (a clean reference slot).
  Isolated rescues (below 25% of the meals) → "isolated hypo(s) — mixed, check
  meals individually", with a lever that says the CR fits on average but points at
  the low meal rather than tightening. A systematic share (≥25%, and at least two)
  → "likely too strong" and no reassuring reference lever. This removes the earlier
  contradictions where a single rescue among many meals produced "too strong" (even
  "too weak → tighten ⚠︎ likely too strong"), or "leave as is" appeared next to a
  hypo-rescue flag.
- The hypo caution lever no longer contradicts the dose direction of the verdict.
  Its "reduce the dose here" wording only appears when the slot is actually too
  strong (or the rescues are systematic); for a slot that is on average too weak
  with a single treated hypo it now reads "a hypo was treated on one meal; check
  that meal, do not tighten the whole slot", so "too weak → tighten" and the
  caution no longer point in opposite directions.
- The hypo caution line now appears whenever a rescue was recorded, not only when
  the slot's median curve itself dips into the hypo range. Previously two slots
  could both carry "hypo treated" in the verdict while only the one with a deep
  median nadir also showed a caution line. When only the rescue signals the low
  (the median curve stays above the hypo threshold), the caution refers to the
  treated low in the window instead of quoting the median nadir value, which would
  understate it.

## [0.6.2] - 2026-08-12
### Fixed
- A slot that is on average too weak but contains a single hypo rescue no longer
  shows the self-contradictory "too weak → tighten ⚠︎ (likely too strong)". Such a
  mix (aggregate too weak, one meal went low) now reads as "a single hypo despite
  an on-average too-weak CR — mixed, check meals individually" instead.

### Changed
- Translated the last remaining German docstring (`_version.py`) to English.

## [0.6.1] - 2026-08-12
### Fixed
- Hypo rescues are no longer invisible to the analysis. Small carb entries below
  the meal threshold (a few grams, typically no bolus, at low glucose) used to be
  dropped entirely, so a meal that caused a treated hypo looked clean and could be
  rated "adequate". Such entries are now read as minors: any minor in a meal's
  postprandial window marks it contaminated, and one with no bolus at glucose
  below the hypo threshold is treated as a hypo rescue.
- A hypo rescue now shows on the slot verdict ("hypo treated" when the slot is
  already "too strong", otherwise "hypo rescue — likely too strong"), the per-meal
  table distinguishes a rescue (⚠︎ H) from plain contamination (⚠︎), and the nadir
  caution reads as an actually treated hypo instead of a mere "secure the window"
  hint when a rescue is present.
- Resolved a safety-relevant contradiction where a slot could read "adequate" and
  "dose fits — leave as is" next to a hypo warning: the reassuring reference lever
  is now suppressed whenever a hypo is present in the window.

## [0.6.0] - 2026-08-11
### Added
- Automatic locale detection for the export format: dates `dd.mm.yyyy`,
  `dd/mm/yyyy` and `yyyy-mm-dd`, and both comma and dot decimal separators are
  now parsed (previously German format only).
- Automatic glucose-unit detection (mg/dL or mmol/L) from the CGM column header.
  The whole report — metrics, target ranges, AGP and all charts, per-meal values
  and derivations — is rendered in the export's unit. GMI is computed on a mg/dL
  mean regardless of display unit. mg/dL exports are unchanged.
- Multilingual report output via gettext (`--lang de|en`, default `de`). All
  user-facing strings in the code and template are now translatable; German and
  English catalogs live under `locale/`. English source strings (msgids), German
  and English `.mo` files are bundled into the binaries. The report language is
  selected at runtime; the German output is unchanged from before.
### Changed
- All code comments and docstrings, the CLI help, the release footers and the
  release scripts are now in English; the changelog is kept in English going
  forward (entries up to 0.5.3 remain German).

## [0.5.3] - 2026-08-10
### Behoben
- „Zu schwach → straffen"-Befund wirkte widersprüchlich, wenn er allein aus dem
  Loop-Mehrbasal kam, das Δ4h in der Tabelle daneben aber negativ war (BZ am
  Fensterende gefallen, weil der Loop kräftig nachgeschoben hat). Die Ableitungen
  ergänzen jetzt einen Achtung-Hinweis, der diesen scheinbaren Widerspruch
  benennt und rät, vor dem Straffen Einzelmahlzeiten und Kontamination zu prüfen.

## [0.5.2] - 2026-08-10
### Geändert
- Fasten-Basalrate wird jetzt als **Mittelwert** der nächtlichen Basalraten
  berechnet (vorher Median). Unter Auto Mode setzt der Loop die Basalrate häufig
  auf 0 aus und fährt dazwischen Spitzen; der Median bildet dann eher ab, wie oft
  ausgesetzt wird, der Mittelwert die tatsächlich gelieferte Insulinmenge — und
  als Referenz fürs Loop-Mehrbasal (eine Menge/Fläche) ist der Mittelwert die
  konsistente Bezugsgröße. Die Slot-Befunde ändern sich dadurch praktisch nicht
  (an zwei realen Datensätzen kein einziger Verdikt-Wechsel), nur die Loop-4h-
  Zahlen verschieben sich leicht.
- Fasten-Fenster um die 5. Stunde erweitert (jetzt 00:00–05:59 statt 00:00–04:59),
  für eine etwas breitere Datenbasis.

### Neu
- Fasten-Basalrate im Report zeigt zusätzlich die nächtliche Streuung
  („Nächte X–Y U/h") und bei stark schwankenden Nächten (Spannweite der
  Nacht-Mittel ≥ 30% des Gesamt-Mittels) einen Vorsicht-Hinweis. So ist
  sichtbar, wie belastbar die Referenz ist — unter Auto Mode kann die
  nächtliche Rate von Nacht zu Nacht stark schwanken.

## [0.5.1] - 2026-08-10
### Behoben
- Baseline-normalisierte Kurve nutzt jetzt dieselbe kontaminationsbereinigte
  Mahlzeitenauswahl wie die Δ4h-Spalte der Tabelle (nur saubere Mahlzeiten,
  Fallback auf alle bei weniger als 3 sauberen). Vorher bezog die Kurve auch
  kontaminierte Mahlzeiten ein und konnte der Tabelle dadurch widersprechen —
  z. B. ein Slot mit „passend"-Befund, dessen Kurve tiefer abfiel als ein als
  „zu stark" bewerteter Slot. Die Legende der normalisierten Kurve weist jetzt
  je Slot aus, ob n saubere Mahlzeiten sind („sauber") oder — bei aktivem
  Fallback — alle („alle"), damit sie nicht widersprüchlich zur „clean"-Spalte
  der Tabelle wirkt.

## [0.5.0] - 2026-08-10
### Neu
- Zusätzliche baseline-normalisierte Kurve unter der CR-Tabelle („Verlauf
  relativ zum Mahlzeitbeginn"): Jede Mahlzeit wird auf ihren eigenen
  Ausgangswert bei Minute 0 bezogen, dann erst gemittelt. Damit wird der
  typische Netto-Verlauf sichtbar, der zur Spalte Δ4h passt — die absolute
  Median-Kurve kann einen Netto-Abfall verbergen, weil dort Start und Ende
  unabhängig über alle Mahlzeiten gemittelt werden. Kurze Erläuterung im Report
  ergänzt.

### Geändert
- Release-CI in zwei plattformspezifische Dateien getrennt, weil Gitea Actions
  an `if:`-Ausdrücken nur `always()` unterstützt und Jobs mit `needs` auf
  übersprungene Jobs dort in „Wartend" hängen bleiben — eine gemeinsame Datei
  mit Plattform-Weichen funktioniert deshalb nicht zuverlässig.
  `.github/workflows/build-release.yml` (nur GitHub) baut Linux- und
  Windows-Binary und hängt sie über die bewährte Action
  `softprops/action-gh-release` ans Release (Build-Matrix + ein separater
  Release-Job, damit die parallelen Matrix-Jobs nicht um denselben Release
  konkurrieren). `.gitea/workflows/release.yml` (nur Gitea) erstellt einen
  schlanken Quellcode-Release **ohne** Binaries in einem einzelnen Job ohne
  `needs`, per `curl` gegen die Gitea-REST-API (dort gibt es keine
  gleichwertige Release-Action). Wer auf Gitea ein Binary braucht, nimmt es von
  GitHub oder baut per `pip install` + PyInstaller selbst.
- DCO-Sign-off-Prüfung auch für Gitea gespiegelt (`.gitea/workflows/dco.yml`),
  da Gitea bei vorhandenem `.gitea/`-Verzeichnis das `.github/`-Verzeichnis
  vollständig ignoriert. Die Gitea-Variante ermittelt die Commit-Basis robust
  über die Branch-Referenzen, falls der PR-Event-Kontext die SHAs nicht wie auf
  GitHub bereitstellt.

## [0.4.6] - 2026-08-07
### Behoben
- SEA-Hinweis (früher hoher Peak → Spritz-Ess-Abstand prüfen) erschien bisher
  nicht bei Slots mit „passend"-Befund, selbst wenn die Kurve einen deutlichen
  frühen Peak zeigte (Dosis-Ampel und Timing-Hinweis sind unabhängig
  voneinander). Der Referenz-Text passt sich entsprechend an („Dosis passt —
  so belassen; Timing siehe SEA-Hinweis oben") statt weiterhin pauschal
  „Dosis & Timing passen" zu behaupten.

## [0.4.5] - 2026-08-07
### Neu
- Eigene Tageszeit-Slots über `--slots-file <pfad.json>` — funktioniert auch mit
  den PyInstaller-Binaries (reine JSON-Datei, kein Codezugriff nötig). Vorlage
  liegt unter `example-data/slots.example.json`; die eigene Kopie (üblicherweise
  `slots.json`) ist per `.gitignore` von der Versionierung ausgenommen. Klare
  Fehlermeldungen bei ungültigem Format statt stillem Falschverhalten.
- Report zeigt jetzt die Slot-Zeitfenster als Legende unter der
  CR-Beurteilungs-Tabelle (z. B. „Frühstück = 05:00–10:00 Uhr"), direkt aus
  `SLOTS` abgeleitet — bei geänderten Zeiten automatisch aktuell.

### Behoben
- Ein neuer Eintrag in `SLOTS` tauchte bisher nicht überall auf: `MAIN_SLOTS`,
  die CR-Beurteilungs-Tabelle und die stdout-Zusammenfassung pflegten je eine
  eigene, unabhängige hart codierte Slot-Liste. Alle drei leiten sich jetzt aus
  `SLOTS` ab; ein neuer Slot mit echtem Zeitfenster erscheint automatisch
  überall (Tabelle, Ableitungen, Kurven-Chart, stdout) und bekommt automatisch
  eine Farbe aus einer Palette zugewiesen.

## [0.4.4] - 2026-08-04
### Neu
- Slot-Befund als „⚠︎ (wenig saubere Mahlzeiten)" gekennzeichnet, wenn weniger
  als 3 unkontaminierte Mahlzeiten vorliegen und die Aussage deshalb (mit) auf
  Fenstern beruht, in denen eine weitere Mahlzeit hineinspielt. Tabellenzeile
  entsprechend visuell abgeschwächt statt in voller Signalfarbe.

## [0.4.3] - 2026-08-04
### Neu
- Changelog (Keep a Changelog) eingeführt; Release-Notes werden jetzt aus dem
  passenden `CHANGELOG.md`-Abschnitt erzeugt und um den festen Hinweis-Footer
  (Disclaimer + Binaries) ergänzt.

## [0.4.2] - 2026-08-03
### Behoben
- Ableitungs-Karte: keine Straffungs-Empfehlung mehr, wenn das Loop-Signal dem
  widerspricht (z. B. „zu schwach" durch erhöhtes Δ4h, obwohl der Loop weniger
  Basal gefahren hat — typischerweise bei kleiner Fallzahl oder Ausreißer).

## [0.4.1] - 2026-08-02
### Behoben
- Irreführende Überschrift in der Ableitungs-Karte („fällt unter den Ausgangswert",
  obwohl die Kurve zur Ausgangslage zurückkehrte).

### Geändert
- Realistischere Beispieldaten.

## [0.4.0] - 2026-08-01
### Neu
- Tages-Insulinsumme (TDD) in der Tagesübersicht mit Bolus-/Basal-Aufteilung,
  z. B. „TDD 35.7 U (Bolus 17.1 / Basal 18.6)", gelesen aus dem Export.

### Behoben
- Legenden-Fix in der Tagesübersicht.

### Intern
- Laufende CI-Pflege.

## [0.3.1] - 2026-08-01
### Neu
- Versionsanzeige in der Kopfzeile, automatisch aus Git abgeleitet — kann nicht
  mehr von den Release-Tags abweichen.

### Behoben
- Legenden-Fix in der Tagesübersicht.

## [0.3.0] - 2026-07-31
### Neu
- Optionale Tagesübersicht (`-d` / `--daily`): ein seitenbreites Panel je Tag mit
  Glukoseverlauf, Bolus, Kohlenhydraten und Basalrate (ähnlich Glooko/CamAPS).
  Standardmäßig aus, damit der Report kompakt bleibt.

## [0.2.2] - 2026-07-31
### Verbessert
- Schnellerer, ruhigerer Start der Binaries: matplotlib-Font-Cache wird nicht mehr
  bei jedem Aufruf neu gebaut (fester Cache-Ort statt Onefile-Temp).

## [0.2.1] - 2026-07-30
### Neu
- Eigenständige Binaries für Linux und Windows am Release
  (`loop-cr-review-linux`, `loop-cr-review-windows.exe`), automatisch über GitHub
  Actions gebaut, Report-Template enthalten — kein Python nötig.

## [0.2.0] - 2026-07-29
### Neu
- „Ableitungen aus der Kurvenform & mögliche Ansätze": pro Slot Kurven-Metriken
  (Peak-Höhe/-Zeit, Tiefpunkt, Spätanstieg) und daraus abgeleitete Stellschrauben
  (SEA, Dosis, Fettanteil …).
- `CR_eff` als Richtungsgröße erklärt.
- Beispieldaten zum Ausprobieren.

## [0.1.1] - 2026-07-29
### Behoben
- Liest alle nummerierten Glooko-Export-Dateien (`cgm`/`bolus`/`basal` `_*.csv`).

## [0.1.0] - 2026-07-29
### Neu
- Erste öffentliche Version: wertet einen CamAPS-FX-/Glooko-Export aus und erzeugt
  einen eigenständigen HTML-Report mit AGP, Konsens-Metriken und einer Loop-aware
  Beurteilung der Kohlenhydrat-Verhältnisse (CR) pro Tageszeit-Slot.

[Unreleased]: https://github.com/peisenh/loop-cr-review/compare/v0.8.3...HEAD
[0.8.3]: https://github.com/peisenh/loop-cr-review/compare/v0.8.2...v0.8.3
[0.8.2]: https://github.com/peisenh/loop-cr-review/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/peisenh/loop-cr-review/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/peisenh/loop-cr-review/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/peisenh/loop-cr-review/compare/v0.6.3...v0.7.0
[0.6.3]: https://github.com/peisenh/loop-cr-review/compare/v0.6.2...v0.6.3
[0.6.2]: https://github.com/peisenh/loop-cr-review/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/peisenh/loop-cr-review/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/peisenh/loop-cr-review/compare/v0.5.3...v0.6.0
[0.5.3]: https://github.com/peisenh/loop-cr-review/compare/v0.5.2...v0.5.3
[0.5.2]: https://github.com/peisenh/loop-cr-review/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/peisenh/loop-cr-review/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/peisenh/loop-cr-review/compare/v0.4.6...v0.5.0
[0.4.6]: https://github.com/peisenh/loop-cr-review/compare/v0.4.5...v0.4.6
[0.4.5]: https://github.com/peisenh/loop-cr-review/compare/v0.4.4...v0.4.5
[0.4.4]: https://github.com/peisenh/loop-cr-review/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/peisenh/loop-cr-review/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/peisenh/loop-cr-review/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/peisenh/loop-cr-review/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/peisenh/loop-cr-review/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/peisenh/loop-cr-review/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/peisenh/loop-cr-review/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/peisenh/loop-cr-review/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/peisenh/loop-cr-review/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/peisenh/loop-cr-review/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/peisenh/loop-cr-review/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/peisenh/loop-cr-review/releases/tag/v0.1.0
