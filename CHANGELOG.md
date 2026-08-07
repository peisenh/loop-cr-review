# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier dokumentiert.
Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
das Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

> Kein Medizinprodukt — nur Analyse. Keine Diagnose, keine Therapieempfehlung.

## [Unreleased]

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

[Unreleased]: https://github.com/peisenh/loop-cr-review/compare/v0.4.5...HEAD
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
