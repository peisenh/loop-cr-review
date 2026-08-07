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
