# Android architecture (POC)

The existing web application is intentionally not rewritten, and the analysis is
not copied either: `sync-analysis.sh` — and the Gradle task `syncAnalysis` before
every build — take it from the repository this project sits in.

1. `MainActivity` starts the embedded Python runtime (Chaquopy).
2. `android_server.py` sets writable `MPLCONFIGDIR`, points Flask at bundled `templates/`, binds **127.0.0.1** with an ephemeral port.
3. WebView loads `http://127.0.0.1:<port>/` only (other hosts blocked).
4. Upload form posts ZIP/CSV to Flask; analysis runs on device.
5. Temp dirs stay ephemeral as in the desktop web implementation.
6. Cleartext HTTP is allowed only for localhost via `network_security_config.xml`.

Next hardening (not in this POC): foreground service during report build,
Activity Result API instead of `startActivityForResult`, pin dependency hashes,
shrink ABIs for release. See the README for what is still open.
