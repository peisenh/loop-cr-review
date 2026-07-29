# data/ — eigene Exporte (nicht im Repo)

Ablageort für die **eigenen** entpackten Glooko-/CamAPS-Exporte.

**Datenschutz:** Der Inhalt dieses Ordners ist per `.gitignore` ausgenommen — echte
CGM-/Pumpendaten landen also **nicht** im Repository und werden nicht committet. Nur diese
`README.md` und die `.gitignore` sind versioniert.

## Benutzung

Export-ZIP hier entpacken, z. B.:

```
data/
└── 2026-jul-4w/
    ├── cgm_data_1.csv
    ├── cgm_data_2.csv
    └── Insulin data/
        ├── bolus_data_1.csv
        └── basal_data_1.csv
```

Dann aus dem Projektwurzel-Verzeichnis:

```bash
python3 loop_cr_review.py data/2026-jul-4w
```

Zum reinen Ausprobieren ohne eigene Daten gibt es den synthetischen Beispiel-Export unter
[`../example-data/`](../example-data/).
