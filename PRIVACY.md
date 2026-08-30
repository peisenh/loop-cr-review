# Datenschutzerklärung — Loop CR Review

Stand: 30. August 2026

Diese Erklärung gilt für die Android-App, die Desktop-Programme und
die Kommandozeile vom GitHub-Release sowie für den Betrieb aus dem
Quellcode. Loop CR Review ist kein Medizinprodukt und stellt keine
Diagnose oder Therapie.

## Was die Software tut

Die Software wertet einen vom Nutzer bereitgestellten CamAPS-FX-
oder Glooko-Export aus und erzeugt einen HTML-Report (AGP, Kennzahlen,
CR-Slots). Die Auswertung läuft **auf dem Gerät bzw. Rechner des
Nutzers**. Wir betreiben dafür keine Cloud und kein Nutzerkonto.

## Welche Daten vorkommen

- Inhalt des Exports (Glukose, Insulin, Mahlzeiten, Geräte-/Namenfelder
  soweit sie in der Datei stehen)
- daraus erzeugter HTML-Report
- optionale Slot-Konfiguration, die der Nutzer selbst vorgibt

Diese Daten werden zur Auswertung in einen lokalen temporären Bereich
kopiert und nach der Report-Erzeugung bzw. nach Ablauf des lokalen
Jobs wieder entfernt. Speichert der Nutzer den Report über den
Systemdialog, liegt die Kopie dort, wo der Nutzer sie hinstellt
(lokale Datei oder eine Cloud-App seiner Wahl). Das ist dann kein
Upload durch uns.

## Was wir nicht tun

- keine Übertragung an Server von uns
- keine Analyse- oder Werbe-IDs
- kein Crash- oder Nutzungs-Upload an uns
- kein Verkauf von Daten

## Android-App

Internetzugriff dient dem lokalen WebView (Flask auf 127.0.0.1) und
dem Öffnen von Links im Systembrowser. Es gibt keine Kontoanmeldung.
Backup der App-Daten ist in der APK ausgeschaltet.

## Selbst gehostete Weboberfläche

Wer die optionale `webapp` im eigenen Netz startet, ist für diesen
Server selbst verantwortlich. Das ist nicht die Android-App im
Play Store und nicht die Desktop-Builds vom GitHub-Release.

## Kontakt

Fragen und Hinweise: https://github.com/peisenh/loop-cr-review/issues

Quellcode: https://github.com/peisenh/loop-cr-review
