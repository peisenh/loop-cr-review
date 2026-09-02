# Privacy statement — Loop CR Review

[🇩🇪 Deutsch](PRIVACY.md) · **🇬🇧 English**

As of: 1 September 2026

This statement covers the Android app, the desktop programs and the
command line from the GitHub release, as well as running from source.
Loop CR Review is not a medical device and provides neither diagnosis
nor treatment.

## What the software does

The software analyses an export supplied by the user and produces an
HTML report (AGP, key figures, CR slots). Glooko/CamAPS FX, LibreView,
Dexcom Clarity and Nightscout are supported. The analysis runs **on the
user's own device or machine**. We operate no cloud and no user account
for it.

## Which data is involved

- the contents of the export (glucose, insulin, meals, device and name
  fields as far as they appear in the file)
- the HTML report produced from it
- an optional slot configuration the user provides

For the analysis this data is copied into a local temporary area. The
export is deleted as soon as the report has been built from it; the
report itself follows a quarter of an hour later at the latest, or
immediately when it is downloaded directly. The Android app removes both
when it is closed. If the user saves the report through the system
dialog, that copy sits wherever the user puts it — a local file, or a
cloud app of their choosing. That is not an upload by us.

## What stays in the browser

The browser keeps what was set in the form in cookies: language, meal
window, the three checkboxes and any custom slot times, so none of it has
to be entered again for every report. Those are settings and times of day,
not health data. They go to the analysis running on the same device
and do not leave it. "Back to default" in the form removes them.

## What we do not do

- no transfer to servers of ours
- no analytics or advertising identifiers
- no crash or usage upload to us
- no selling of data

## Android app

Internet access serves the local WebView (Flask on 127.0.0.1) and opening
links in the system browser. The local server only answers requests
carrying a secret generated at start-up, so other apps on the device
cannot reach it. There is no account sign-in. Backup of the app's data is
switched off in the APK.

## Self-hosted web interface

Anyone who runs the optional `webapp` on their own network is responsible
for that server themselves. It is not the Android app from the Play Store
and not the desktop builds from the GitHub release.

## Contact

Questions and remarks: https://github.com/peisenh/loop-cr-review/issues

Source code: https://github.com/peisenh/loop-cr-review
