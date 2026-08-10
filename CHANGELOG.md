# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier dokumentiert.
Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
das Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

> Kein Medizinprodukt — nur Analyse. Keine Diagnose, keine Therapieempfehlung.

## [Unreleased]

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

[Unreleased]: https://github.com/peisenh/loop-cr-review/compare/v0.5.3...HEAD
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
