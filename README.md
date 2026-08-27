<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo-readme-dark.svg">
    <img alt="loop-cr-review" src="docs/logo-readme-light.svg" width="440">
  </picture>
</h1>

**🇩🇪 Deutsch** · [🇬🇧 English](README.en.md)

**Loop-aware Carb-Ratio Review** — CR-Beurteilung aus realen CamAPS-FX-Daten.

**Nur CamAPS FX (Auto Mode).** Andere AID-Systeme sind nicht unterstützt — siehe Abschnitt „Unterstützte Systeme“.

Wertet einen CamAPS/Glooko-Export aus und erzeugt einen eigenständigen HTML-Report mit Ambulatory Glucose Profile (AGP), Konsens-Metriken und einer **Loop-aware Beurteilung der Kohlenhydrat-Verhältnisse (CR)** pro Tageszeit-Slot.

![Beispiel-Report von loop-cr-review](docs/screenshot.png)

*Beispiel-Report mit synthetischen Demo-Daten ([vollständiger Report](docs/screenshot_full.png)).*

---

## ⚠️ Wichtiger Hinweis — bitte zuerst lesen

> **Dies ist kein Medizinprodukt und dient ausschließlich der Analyse.**
>
> - Das Tool **stellt keine Diagnose** und **keine Therapieempfehlung**. Es wertet lediglich bereits vorhandene CGM- und Pumpendaten statistisch aus.
> - Die Ergebnisse sind **ausschließlich als Gesprächsgrundlage für das Diabetes-Team** gedacht.
> - **Ändere Insulin-, CR-, Korrektur- oder sonstige Therapieeinstellungen niemals ohne Rücksprache und Freigabe durch das behandelnde Diabetes-Team.**
> - Es besteht **keine Gewähr** für Richtigkeit, Vollständigkeit oder Eignung für einen bestimmten Zweck. Nutzung auf eigene Verantwortung.
> - Unter Hybrid-Closed-Loop (CamAPS FX Auto Mode) sind die Auswertungen durch die laufende Loop-Kompensation und die Algorithmus-Adaption **konfundiert** — sie sind Indizien, keine Beweise.

---

## Was es macht

- **AGP** (Perzentile 5/25/50/75/95 über 24 h) und **mediane Postprandial-Verläufe** je Slot.
- **Konsens-Metriken** (Battelino 2019): Ø-Glukose, GMI, CV, TIR/TITR/TBR/TAR, Sensor-Wear.
- **Loop-aware CR-Beurteilung** pro Slot (Frühstück / Mittag / Abend) mit datengetriebenem Befund (zu schwach / zu stark / passend) und Per-Mahlzeit-Detailtabelle.
- **Ableitungen aus der Kurvenform**: pro Slot Kurven-Metriken (Peak-Höhe/-Zeit, Tiefpunkt, Spätanstieg) und daraus abgeleitete Kandidaten-Stellschrauben (SEA/Spritz-Ess-Abstand, Dosis, Fett/Protein, Hypo-Achtung) — als Hypothesen fürs Team, plus Klarstellung von `CR_eff` als Ansatz statt Zielwert.
- Alles Patientenbezogene (Name, Gerät, Zeitraum, Interpretation) wird **aus den Daten** gezogen, nichts ist hartcodiert.

## Kontext: CamAPS FX & Glooko

**CamAPS FX** ist eine App (CamDiab), die den Cambridge-Hybrid-Closed-Loop-Algorithmus (MPC) umsetzt. Sie **moduliert die Basalinsulin-Abgabe** laufend (erhöhen / senken / aussetzen, ca. alle 8–12 min), um den Glukosewert im Zielbereich zu halten; **Mahlzeitenboli** gibt die nutzende Person selbst an, berechnet über das Kohlenhydrat-Verhältnis (CR). Kombiniert wird sie mit CGM-Sensoren (z. B. FreeStyle Libre 3, Dexcom) und kompatiblen Pumpen (z. B. YpsoPump). „Auto Mode" bezeichnet den geschlossenen Regelkreis.

**Glooko** ist eine Diabetes-Datenplattform. CamAPS lädt CGM-, Bolus- und Basaldaten dorthin hoch; von dort exportiert man ein Daten-ZIP mit den CSV-Dateien, die dieses Tool einliest.

**Datenfluss:** CamAPS FX (Auto Mode) → Glooko → CSV-Export (ZIP) → `loop-cr-review` → HTML-Report. Mit „Glooko/CamAPS-Export" ist die aus Glooko heruntergeladene ZIP-Datei mit CamAPS-Daten gemeint.

Dasselbe CamAPS kann zusätzlich in **Nightscout** landen (`entries` / `treatments`). Der Report erkennt so einen Dump und bleibt dort standardmäßig im **Lite-Modus**: die Beurteilung stützt sich allein auf den Glukoseverlauf, die Loop-Größen bleiben leer. Sie kommen nur mit `--assume-camaps` bzw. dem Häkchen im Upload dazu.

## ⚠️ Unterstützte Systeme — nur CamAPS FX

> **Dieses Tool ist ausschließlich für CamAPS FX (Auto Mode) entwickelt und getestet.**

Die Kernmethode setzt darauf, dass CamAPS Auto-Korrekturen als **moduliertes Basal** liefert. Das Loop-Mehrbasal im Mahlzeitfenster beschreibt zusätzliche Auto-Mode-Aktivität; sie *kann* zu einer zu schwachen/starken CR passen, ist bei realem CamAPS aber nicht spezifisch dafür. Andere Systeme funktionieren anders:

- **Tandem Control-IQ, Omnipod 5 u. a.** geben Auto-Korrekturen teils als **Boli** ab. Diese tauchen dann nicht im Basal auf → das Loop-Mehrbasal unterschätzt die Kompensation, der Befund wird verfälscht.
- **Nightscout:** Dump `entries.json` + `treatments.json` (API, kein Live-Abruf). CGM aus `sgv`, Mahlzeiten aus Meal/Correction Bolus, Basal aus `Temp Basal`. Zeiten: UTC aus dem ISO-String, lokale Uhr über das CGM-`utcOffset` (Treatment-Offset 0 wird ignoriert). **Default ist Lite** — Teil 2 nur mit `--assume-camaps`, und nur wenn das wirklich CamAPS über NS ist. AAPS/Loop über Nightscout nicht als CamAPS behandeln.
- **LibreView:** eine Glukose-CSV (Typen 0/4/5). Immer Lite — ohne Basal keine Loop-Größen.
- **Dexcom Clarity:** die CSV aus dem Clarity-Export (`EGV`/`Carbs`/`Insulin`-Zeilen).
  Kohlenhydrate und Insulin nur, soweit in der Dexcom-App protokolliert; langwirksames
  Insulin zählt nicht als Mahlzeitenbolus. Immer Lite — ohne Basal keine Loop-Größen.

**Was Lite-Quellen zeigen.** Ohne Basalspur entfallen nur die Loop-Größen — Loop-Mehrbasal,
`CR_eff` und die Fasten-Basalrate. Alles, was die Glukosekurve allein hergibt, bleibt: die
Rückkehr Δ4h, die daraus folgende CR-Beurteilung je Slot, Stabilität und Streuung sowie
sämtliche Ableitungen aus der Kurvenform. Es bleibt die klassische Betrachtung — so viel
Bolus auf so viele Kohlenhydrate, und dort stand der Zucker vier Stunden später. Ohne Loop,
der die Auslenkung glättet, ist dieses Signal sogar direkter als unter CamAPS.


Für andere Loops ist eine Nutzung **mit Anpassungen denkbar**, aber nicht getestet — insbesondere müssten (1) die Export-Spalten gemappt und (2) Auto-Korrektur-**Boli** in den „Loop-Mehrbasal"-Term einbezogen werden. Ohne diese Anpassungen sind die Ergebnisse für Nicht-CamAPS-Systeme nicht gültig.

## Die zentrale Idee

Unter CamAPS FX Auto Mode ändert der Algorithmus nach der Mahlzeit oft das **Basal**. Der Blutzucker kann trotzdem zur Baseline zurückkehren — ein reiner Kurven-Return-Test sagt dann wenig. Was der Report zusätzlich zeigt, ist das im Mahlzeitfenster gelieferte Extra-Basal:

```
Loop-Mehrbasal   = ∫ (Basalrate − Fasten-Basal) dt   über das Fenster nach der Mahlzeit
CR_eff           = CHO / (Mahlzeitbolus + Loop-Mehrbasal)
```

Positives Loop-Mehrbasal kann zu einer zu schwachen CR passen, ist bei CamAPS aber nicht spezifisch dafür.

## Installation

Debian/Ubuntu über Systempakete (empfohlen, z. B. im Homelab):

```bash
sudo apt install python3-numpy python3-matplotlib python3-jinja2
```

Oder plattformunabhängig über pip (ggf. in einem venv):

```bash
pip install -r requirements.txt
```

### Fertige Binaries (ohne Python)

Für jedes Release werden über GitHub Actions eigenständige Executables gebaut und angehängt
(`loop-cr-review-linux`, `loop-cr-review-windows.exe`) — herunterladen, ausführbar machen, fertig.
Das Report-Template ist im Binary enthalten.

Selbst bauen (auf der jeweiligen Plattform, kein Cross-Compile):

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --name loop-cr-review \
  --add-data "templates/report.html.j2:templates" loop_cr_review.py   # Windows: ";" statt ":"
```

## Nutzung

Drei Wege — einer genügt: die **Kommandozeile** (1), das **Web-Frontend
fürs Homelab** (2) oder die **Desktop-App** (3).

### 1 · Kommandozeile

```bash
# Glooko-Export entpacken, dann:
python3 loop_cr_review.py <export_ordner>            # Default: 4-h-Fenster
python3 loop_cr_review.py .                          # Export liegt im aktuellen Ordner
python3 loop_cr_review.py <export_ordner> -w 3.5     # anderes Fenster (Stunden)
python3 loop_cr_review.py <export_ordner> --lang en  # Report auf Englisch (Default: de)
python3 loop_cr_review.py <ns-ordner>                # Nightscout: entries.json + treatments.json → Lite
python3 loop_cr_review.py <ns-ordner> --assume-camaps  # NS: CamAPS-Teil 2 einschalten
python3 loop_cr_review.py <libreview-ordner>          # LibreView-CSV → immer Lite
python3 loop_cr_review.py <clarity-ordner>            # Dexcom-Clarity-CSV → immer Lite
python3 loop_cr_review.py <export_ordner> --span      # nur Von–Bis ausgeben
python3 loop_cr_review.py <export_ordner> --from 2026-08-01 --to 2026-08-14
python3 loop_cr_review.py <export_ordner> -o report.html
python3 loop_cr_review.py <export_ordner> -t <template_ordner>
```

| Option | Bedeutung | Default |
| --- | --- | --- |
| `export_dir` | Ordner mit Glooko-Export, Nightscout-Dump, LibreView- oder Clarity-CSV. **Pflichtangabe**; gesucht wird bis zwei Ebenen darunter | — |
| `-w, --window-hours` | postprandiales Auswertungsfenster (h) | `4.0` |
| `--dark-charts` | zusätzlich dunkle Chart-PNGs (AGP, Slot-Kurven, Baseline-Norm, und Tagesgraphen bei `-d`); ohne Option nur helle Charts | aus |
| `--assume-camaps` | Loop-Größen (Loop-Mehrbasal, CR_eff) auch für Nightscout. LibreView und Clarity bleiben Lite. Default aus | aus |
| `--span` | nur CGM-Zeitraum ausgeben, kein Report | aus |
| `--from` / `--to` | Kalendertage YYYY-MM-DD (einschließlich) | ganzer Export |
| `-d, --daily` | Tagesübersicht (kleine Tagesprofile je Kalendertag) mit ausgeben | aus |
| `--slots-profile` | `default` · `extended` (05–11/11–15/15–22) · `with_snacks` (Snacks 09–11 und 15–17) | `default` |
| `--slots-file` | Eigene Tageszeit-Slots aus JSON-Datei (siehe `example-data/slots.example.json`); hat Vorrang vor dem Profil | eingebaute Slots |
| `--lang` | Report-Sprache (`de` oder `en`) | `de` |
| `-o, --out` | Ausgabe-HTML | `<name>_loop-cr-review_<fenster>.html` |
| `-t, --template-dir` | Ordner mit `report.html.j2` | `./templates` |

**PDF:** Report im Browser öffnen → Drucken → „Als PDF speichern" (Karten sind gegen Seitenumbrüche geschützt).

Fertige CLI-Binaries (`loop-cr-review-linux` ~50–60 MB, `loop-cr-review-windows.exe`
~30–40 MB) hängen an jedem Release und brauchen kein Python. Sie sind unsigniert —
siehe den Hinweis zum ersten Start unter [3 · Desktop-App](#3--desktop-app-doppelklick).

### 2 · Web-Frontend (Homelab)

Eine kleine Flask-App bietet dieselbe Auswertung im Browser: Glooko-ZIP, Nightscout-ZIP
(`entries.json` + `treatments.json`) oder LibreView-CSV. Nach der Dateiauswahl kommt
der volle Zeitraum (Von/Bis), danach der Report. Beides sind getrennte Requests;
Während der Report gebaut wird, liegen Upload und Ergebnis in einem
privaten Ordner im System-Temp-Verzeichnis. Der Export wird gelöscht, sobald der
Report fertig ist; der Report selbst spätestens nach 15 Minuten, oder sofort mit
„Herunterladen". Der Report erscheint in einem Rahmen (Neuer Report / Speichern);
die gespeicherte HTML ist dieselbe Datei wie von der Kommandozeile. Nightscout bleibt Lite, außer Häkchen
„CamAPS-Auswertung erzwingen“. Gedacht für den **privaten Betrieb im Heimnetz,
nicht für öffentliches Hosting**.

```bash
# mit Docker (empfohlen)
cp docker-compose.example.yml docker-compose.yml   # bei Bedarf anpassen
docker compose up --build                          # http://<homelab-ip>:8000

# oder ohne Docker
pip install -r requirements.txt -r requirements-web.txt
python3 webapp.py                                  # http://127.0.0.1:8000
```

Das Formular bietet dieselben Optionen wie die Kommandozeile — Sprache,
Mahlzeitfenster, Tagesübersicht — dazu einen Download-Schalter und die
Tageszeit-Slots, wahlweise als Standard, über einen eingebauten Feld-Editor oder
als JSON-Upload. `docker-compose.example.yml` enthält einen optionalen,
auskommentierten Traefik-Block für HTTPS + Basic-Auth, falls du einen Reverse
Proxy davorsetzen willst; die echte `docker-compose.yml` ist gitignored, damit
lokale Einstellungen privat bleiben. Es gilt derselbe Hinweis **kein
Medizinprodukt** wie für die Kommandozeile.

### 3 · Desktop-App (Doppelklick)

Fertige Binaries starten dasselbe Frontend in einem nativen Fenster — ohne
Python, Docker oder Browser-Tab. Passende Datei von der Release-Seite laden:

- **Windows 10 / 11 (empfohlen):** `loop-cr-review-gui-windows.exe` (~35–45 MB)
  Schlank, nutzt **Edge WebView2** (unter Win10/11 in der Regel schon installiert).
- **Ältere Windows-Versionen / ohne WebView2:** `loop-cr-review-gui-windows-qt.exe` (~245–255 MB)
  Volles **Qt WebEngine** mitgeliefert — größer, dafür unabhängig von WebView2
  (z. B. wenn der schlanke Build scheitert oder WebView2 fehlt).
- **Linux:** `loop-cr-review-gui-linux` (~275–285 MB, Qt WebEngine mitgeliefert)
  Einmalig ausführbar machen: `chmod +x loop-cr-review-gui-linux`

**Erster Start unter Windows.** Die Binaries sind **nicht signiert** (ein
Signaturzertifikat ist für dieses Projekt nicht vorgesehen), deshalb meldet
sich SmartScreen beim ersten Start mit „Der Computer wurde durch Windows
geschützt“. Wer der Quelle vertraut: **Weitere Informationen → Trotzdem
ausführen**. Gegebenenfalls muss die Datei nach dem Download noch über
*Eigenschaften → Zulassen* freigegeben werden. Wer keine unsignierte Datei
ausführen möchte, prüft die SHA-256-Summe neben dem Asset auf der
Release-Seite oder startet aus dem Quellcode.

Oder aus dem Quellcode:

```bash
# Linux / Windows mit Qt
pip install -r requirements-gui.txt && python3 gui.py

# Windows schlank (WebView2, ohne Qt)
pip install -r requirements-gui-webview2.txt && python3 gui.py
```

Alles läuft lokal; die Daten verlassen den Rechner nicht.


## Datenschutz & Homelab (kurz)

> Keine Rechtsberatung — nur technische Einordnung für den **selbst betriebenen** Einsatz.

- **CLI und Desktop-App:** Auswertung nur lokal; der Export und der HTML-Report bleiben auf dem Rechner. Es gibt keinen Netz-Upload durch das Tool.
- **Web-Frontend:** für das **private Heimnetz** gedacht, nicht für öffentliches Internet. Der Upload landet in einem temporären Verzeichnis und wird gelöscht, sobald der Report daraus gebaut ist; der Report folgt spätestens nach einer Viertelstunde. Absichtlich keine Persistenz und kein Analyse-Logging der Dateiinhalte.
- **Gesundheitsdaten** (CGM/Pumpe) sind besonders schützenswert. Wer den Dienst *anderen* zugänglich macht (auch im LAN), trägt die Verantwortung für Zugriffsschutz (z. B. nur vertrauenswürdige Nutzer, optional HTTPS + Basic-Auth hinter Traefik wie in `docker-compose.example.yml`).
- **Öffentliches Hosting** (freies Internet, Accounts, Speicherung) ist **nicht** der vorgesehene Betrieb und würde deutlich strengere Anforderungen (u. a. Rechtsgrundlage, Transparenz, TOMs, oft DSFA) auslösen — dafür ist dieses Projekt nicht ausgelegt.
- **Impressum / Datenschutzerklärung** braucht man typischerweise, wenn man einen Dienst *geschäftsmäßig* oder öffentlich anbietet — nicht für den reinen Eigengebrauch auf dem eigenen Rechner. Bei Unsicherheit: selbst prüfen oder fachlich beraten lassen.

## Beispieldaten zum Ausprobieren

Im Ordner [`example-data/`](example-data/) liegt ein vollständiger, **rein synthetischer**
Beispiel-Export (Patient „Alex Beispiel", 14 Tage, CamAPS FX / Libre 3 / YpsoPump) — keine echten
Patientendaten. Damit lässt sich das Tool ohne eigenen Export testen:

```bash
python3 loop_cr_review.py example-data
```

Für das **Web-Frontend** (Upload-Formular) liegt zusätzlich
[`example-data/Alex_Beispiel_Glooko_export.zip`](example-data/Alex_Beispiel_Glooko_export.zip)
bereit — ein Glooko-ähnliches ZIP nur mit den CSV-Dateien. Nach
`python3 webapp.py` oder `docker compose up --build` die Datei unter
http://127.0.0.1:8000 hochladen.

Der erzeugte Report entspricht dem Screenshot oben.

Eigene Exporte legst du am besten unter [`data/`](data/) ab — der Inhalt dieses Ordners ist per
`.gitignore` ausgenommen, damit echte Patientendaten nicht ins Repo geraten:

```bash
python3 loop_cr_review.py data/mein-export
```

## Erwartete Eingabe

**Glooko** — entpackter Export mit CamAPS-FX-Daten (siehe „Kontext" oben):


- `cgm_data_*.csv` — CGM-Werte (`Zeitstempel, Glukose (mg/dl), Seriennummer`); Glooko splittet lange Zeiträume auf mehrere nummerierte Dateien (`cgm_data_1.csv`, `cgm_data_2.csv`, …) — alle werden eingelesen
- `Insulin data/bolus_data_*.csv` — Boli inkl. `Kohlenhydrataufnahme (g)` und `Abgegebenes Insulin (E)`
- `Insulin data/basal_data_*.csv` — Basal-Segmente (`Rate`, `Dauer`)

Erkannt werden die gängigen CamAPS-Exportformate automatisch: Datum `dd.mm.yyyy`,
`dd/mm/yyyy` oder `yyyy-mm-dd`, Dezimaltrenner Komma oder Punkt. Die Glukose-Einheit
(**mg/dL** oder **mmol/L**) wird aus dem Spaltenkopf erkannt; der gesamte Report
(Kennzahlen, Achsen, Zielbereiche) erscheint dann in der Einheit des Exports.

**Nightscout** — Ordner oder ZIP mit:

- `entries.json` — CGM (`sgv`, `dateString` / `date`, `utcOffset`)
- `treatments.json` — `Meal Bolus` / `Correction Bolus` / `Temp Basal` (`created_at`, `carbs`, `insulin`, `rate`/`absolute`, `duration`)

Beides von der eigenen Site, z. B. `/api/v1/entries.json?count=100000` und `/api/v1/treatments.json?count=100000` (Token nicht ins Tool). Lite ohne Extra-Schalter.

**LibreView** — eine `*glucose*.csv` von libreview.com (deutsche oder englische Kopfzeile). Verlaufsglukose (Typ 0) plus KH/Insulin (Typen 5/4). Immer Lite.

## Projektstruktur

```
loop-cr-review/
├── loop_cr_review.py          # Logik (Einlesen, Analyse, Charts, Context) + CLI
├── webapp.py                  # optionales Web-Frontend fürs Homelab (Flask)
├── gui.py                     # Desktop-App (pywebview + lokaler Server)
├── templates/
│   ├── report.html.j2         # Darstellung (Jinja2) — Layout/Wording hier anpassen
│   ├── upload.html.j2         # Upload-Formular des Web-Frontends
│   └── viewer.html.j2         # Rahmen um den Report (Neuer Report / Speichern)
├── static/                    # Logo-Assets fürs Web-Frontend
├── example-data/              # synthetischer Beispiel-Export zum Ausprobieren
├── tests/                     # Regressionstests (example-data)
├── data/                      # eigene Exporte (Inhalt per .gitignore ausgenommen)
├── docs/                      # Screenshots + Logo fürs README
├── Dockerfile                 # Container fürs Web-Frontend
├── docker-compose.example.yml # nach docker-compose.yml kopieren (gitignored)
├── requirements.txt           # CLI-Abhängigkeiten
├── requirements-web.txt       # zusätzliche Abhängigkeiten fürs Web-Frontend
├── requirements-gui.txt       # Desktop-App Qt (Linux + Windows full)
├── requirements-gui-webview2.txt  # Desktop-App Windows schlank (WebView2)
├── tools/                     # Validierungsskripte (nicht Teil der Auswertung)
├── VALIDATION.md              # gemessene Belastbarkeit von Streubereich/Stabilität
├── sim/
│   ├── SIMULATION-SPEC.md     # Spezifikation der Methodenvalidierung (Phase A/B, frozen)
│   ├── PHASE_B_DESIGN.md
│   ├── PHASE_B_ROBUST.md
│   └── UPTAKE.md              # Ergebnisse und Schluss
├── README.md
├── CONTRIBUTING.md
├── LICENSE
└── .pylintrc
```

## Methoden-Parameter (datenunabhängig)

Als benannte Konstanten oben in `loop_cr_review.py` gebündelt und anpassbar: Slot-Zeitfenster, Mahlzeit-Mindest-CHO, Merge-Fenster, Fasten-Fenster, Loop-Ratio- und Δ-Schwellen, CR-Abweichungs- und prä-BZ-Schwellen. Die klinischen Zielbereiche (TIR 70–180 usw.) folgen dem internationalen Konsens.

## Grenzen

- Gültig für **angesagte Mahlzeiten**; Confounder (Fett/Protein, Bewegung, Pre-Bolus-Timing, gesplittete/überlappende Boli) sind über Mediane gedämpft, nicht eliminiert.
- Das **Fasten-Basal** als Referenz (Mittel der Nächte) setzt mahlzeit-/korrekturfreie Nächte (00:00–06:00 Uhr) voraus.
- Die aus `CHO/Bolus` abgeleitete CR kann vom Bolusrechner beigemischte Korrekturen enthalten (das Tool weist darauf hin, wenn ein Slot auffällig abweicht).
- CamAPS' Adaption über Tage kann länger bestehende Fehleinstellungen teilweise glätten.
- **Streubereich und Entscheidungsstabilität** beziffern nur, wie empfindlich ein
  Ergebnis von der Auswahl der aufgezeichneten Tage abhängt — nicht, ob die CR
  richtig ist. Wie belastbar diese Zahlen selbst sind (gemessene Deckung,
  Grenzen des Verfahrens): [VALIDATION.md](VALIDATION.md).

## Mitwirken

Beiträge sind willkommen. Das Projekt nutzt einen **DCO-Sign-off** (`git commit -s`); Details im bilingualen [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Lizenz

**GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)** — siehe [`LICENSE`](LICENSE). Jede Quelldatei trägt einen `SPDX-License-Identifier`.

Copyright © 2026 Peter Eisenhauer &lt;github@peter-e.de&gt;

---

*Nochmals: kein Medizinprodukt, keine Therapieempfehlung, keine Gewähr. Änderungen an der Therapie ausschließlich durch das behandelnde Diabetes-Team.*
