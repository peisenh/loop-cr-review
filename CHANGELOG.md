# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).
Entries up to and including 0.5.3 are in German; newer entries are in English.

> Not a medical device — analysis only. No diagnosis, no treatment recommendation.

## [Unreleased]

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

[Unreleased]: https://github.com/peisenh/loop-cr-review/compare/v0.7.0...HEAD
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
