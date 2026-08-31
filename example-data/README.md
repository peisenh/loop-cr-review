# Beispieldaten (synthetisch)

Vollständiger Beispiel-Export im Glooko-/CamAPS-Format zum Ausprobieren des Tools —
**rein synthetisch generiert, keine echten Patientendaten.**

- Patient: „Alex Beispiel" (frei erfunden)
- Zeitraum: 14 Tage, CamAPS FX Auto Mode (FreeStyle Libre 3 / mylife YpsoPump)
- Muster (bewusst zur Demonstration): Frühstück tendenziell zu stark, Mittag zu schwach, Abend passend

Aus dem Projektwurzel-Verzeichnis ausführen:

```bash
python3 loop_cr_review.py example-data
```

## Web-Frontend / Docker

Dieselbe Auswertung per Upload testen: die Datei
`Alex_Beispiel_Glooko_export.zip` in diesem Ordner ist ein Glooko-ähnliches
Archiv (nur die CSV-Dateien, ohne README/Slots) und kann im Web-Formular
unter http://127.0.0.1:8000 hochgeladen werden:

```bash
# Web starten (ohne Docker)
pip install -r requirements.txt -r requirements-web.txt
python3 webapp.py
# dann im Browser ZIP wählen: example-data/Alex_Beispiel_Glooko_export.zip
```

## Eigene Tageszeit-Slots

`slots.example.json` zeigt das Format für eigene Slot-Zeitfenster (z. B. andere Uhrzeiten,
zusätzliche Slots wie „Brunch" oder „Spätmahlzeit"). Als Vorlage kopieren, anpassen und mit
`--slots-file` einbinden:

```bash
cp example-data/slots.example.json slots.json   # eigene Kopie, nicht die example-Datei bearbeiten
python3 loop_cr_review.py example-data --slots-file slots.json
```

Regeln: Reihenfolge = Priorität (erster Treffer gewinnt), `start`/`end` in vollen Stunden
(0–24), genau **ein** Eintrag mit `"start": -1, "end": -1` als Auffangbecken für alles, was in
kein anderes Fenster fällt. Bei ungültigen Angaben bricht das Tool mit einer klaren
Fehlermeldung ab, statt falsche Slots stillschweigend zu verwenden.

Beliebige Namen möglich, z. B. `slots-schule.json`, `slots-urlaub.json`, `slots-test.json` für
unterschiedliche Situationen — einfach den passenden Pfad bei `--slots-file` angeben:

```bash
python3 loop_cr_review.py data/juli-urlaub --slots-file slots-urlaub.json
```

Alle Dateien nach dem Muster `slots*.json` im Projektwurzel-Verzeichnis sind per `.gitignore`
von der Versionierung ausgenommen — nur die Beispiel-/Vorlagendatei hier ist im Repo.

## Lite-Quellen (dieselbe synthetische Person)

Aus dem Glooko-Demo erzeugt, **keine** echten Daten. Name bleibt „Alex Beispiel“.
Kein Basal — der Report ist absichtlich Lite.

```bash
python3 tools/export-example-sources.py   # neu schreiben aus dem Glooko-ZIP/Ordner

python3 loop_cr_review.py example-data/nightscout
python3 loop_cr_review.py example-data/libreview
python3 loop_cr_review.py example-data/clarity
```

Web-Upload: den jeweiligen Ordner zippen oder die einzelne CSV wählen.

| Ordner | Dateien |
|--------|---------|
| `nightscout/` | `entries.json`, `treatments.json` |
| `libreview/` | `Alex_Beispiel_LibreView.csv` |
| `clarity/` | `Alex_Beispiel_Clarity.csv` |
