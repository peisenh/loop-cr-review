# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).
Entries up to and including 0.5.3 are in German; newer entries are in English.

> Not a medical device — analysis only. No diagnosis, no treatment recommendation.

## [Unreleased]

### Added
- `tools/make-play-screenshots.sh`: the store screenshots from the example data,
  at phone size, in both languages. They were taken by hand on a device, which
  meant redoing all of them for every change of wording. Each picture is the
  whole page scrolled to a section — a card cut out on its own looks like a
  fragment rather than the app — and the scroll position comes from a marker the
  script places, not from a guessed offset. Shots are flattened, because browsers
  write PNGs with an alpha channel that the store rejects, and checked against
  the store's limits before upload.
- `SECURITY.md`: how to report a vulnerability. Through GitHub's private
  reporting rather than a public issue, and — since a report from this tool is
  health data — never with a real export attached; the synthetic files in
  `example-data/` are enough to describe any of it. Says what is in scope and
  what is not: a wrong verdict is a regular issue, running the web app on the
  public internet is not a finding.
- `PRIVACY.en.md`: the privacy statement in English, since the store listing has
  an English version too. Both link to each other, and both READMEs now point at
  the right one — they pointed at neither.

### Fixed
- The report is readable on a phone. It had no viewport tag, so a phone laid it
  out at about 980 px and scaled the result down — a wall of tiny text, with none
  of the narrow-screen rules taking effect. With the tag, the wide tables scroll
  sideways instead of being squeezed into a width where no column can be read: a
  shadow at the edge shows there is more, and a line under the table says so. All
  of that applies below 680 px only; on a desktop and in print the tables are
  exactly as before. It became obvious only while photographing the report at
  phone width.
- The privacy statement described the tool as reading a CamAPS or Glooko export
  only; it names all four supported sources now.
- It also said data is removed "after the report is built or when the job
  expires", which is vaguer than what happens: the export goes as soon as the
  report exists, the report a quarter of an hour later at the latest, and the
  Android app clears both when it closes. That the app's local server is closed
  to other apps was missing as well.

## [0.23.0] - 2026-09-01

### Security
- The local server now requires a secret. A loopback port is not private: on
  Android any app holding the INTERNET permission can reach another app's
  127.0.0.1, and on a desktop so can any other local process. Job ids are
  unguessable, so a report could not be read by a stranger, but the form and
  the analysis endpoints were open to anyone on the machine. The Android app
  and the desktop window generate a token at start-up. The WebView presents it in
  the first URL and gets a cookie back; requests the app makes with its own HTTP
  client — saving a report, opening it in a browser — carry it in the URL each
  time. Docker is unaffected: no token set, no check.
- Android: the FileProvider exposed the whole cache directory. It is limited to
  the folder the shared report is written to.
- Android: the picked export stayed in the cache after the app was closed. Both
  it and the shared report are removed in `onDestroy`.

### Added
- Web upload accepts Nightscout `entries.json` and `treatments.json` together,
  without a ZIP. Glooko ZIP and LibreView/Clarity CSV stay as they were.
- Synthetic Lite dumps for Nightscout, LibreView and Dexcom Clarity under
  `example-data/`, rebuilt from the Glooko Alex-Beispiel export
  (`tools/export-example-sources.py`). No real patient data.

### Changed
- The verdicts and the derived hints no longer read as instructions. "too weak →
  tighten" becomes "coverage looks too weak"; the hint that named a CR_eff value
  as a "rough direction" now states what CR_eff came out at, which is what the
  report says elsewhere it is — an approach, not a target. Same for the rest:
  reduce the dose, secure the hypo window, leave as is. The direction is still
  there, the imperative is not.
- The upload page no longer presents the tool as CamAPS-only. It leads with full
  versus glucose-only assessment, the way the README does. A LibreView user used
  to read "tested only for CamAPS FX" and conclude the tool was useless to them,
  although they get a complete assessment.
- README (de/en): lead with full vs lite instead of “CamAPS only”. GRI is listed
  with the metrics that always run; loop CR stays CamAPS-only.
- Local Android APK/AAB builds read the keystore password from
  `android/release.env` (gitignored) or a silent prompt, not from the
  command line.
- Changed detection of glooko/nightscout/libreview data
- Automatic increase of android version code if new version is released

### Fixed
- `prepare-release.sh` changed files before it checked anything. A failing guard —
  an existing tag, an empty `[Unreleased]` — left the Android `versionCode` raised
  in the working tree, and the next attempt raised it again; a versionCode cannot
  be taken back on Play. All checks run first now, and the whole tree has to be
  clean, not just `CHANGELOG.md` — the release commit takes two files and anything
  else staged would have gone in with them.
- A repository URL that could not be read from `CHANGELOG.md` was silently replaced
  with a placeholder that then went into the file. It stops instead.
- Both release scripts use `sed` rather than `grep -oP`, which only exists in GNU
  grep.
- Fixed messages.po

## [0.22.0] - 2026-08-30

### Changed
- Android APK uses numpy 2.3.2 (Chaquopy pypi-upstream) and matplotlib 3.11.1
  built against it (ELF align 0x4000). 16 KB page-size devices work.
  The matplotlib wheel is committed under `android/app/wheels/`; numpy is
  fetched at build time. Notices: `android/app/wheels/NOTICE.md`.
- Android WebView follows the system dark/light theme (`prefers-color-scheme`).
- Android `compileSdk` / `targetSdk` 36. `minSdk` stays 24. versionCode is 4.
- Android WebView only loads the Flask loopback origin (scheme+host+port);
  file/content access in the WebView is off. Slot names in the derived-CR
  HTML note are escaped.
- Print: large cards (AGP, meal curves, CR table) may break across pages; small cards stay intact.

## [0.21.0] - 2026-08-29

### Changed
- Android sideload APK is signed with a shared release keystore locally and
  on GitHub Actions (not the machine debug key). The keystore is not in git.
- Release notes and READMEs no longer call the APK unsigned / debug-signed.

  Installs of 0.20.x must be uninstalled first (different signature).
  versionCode is 3. Package `de.peisenh.loopcrreview` is registered for
  distribution outside Play.

## [0.20.1] - 2026-08-29

### Added
- Android viewer bar: Print opens the system print dialog (including Save as PDF).

### Changed
- Android project lives in `android/` (was `poc/android-chaquopy/`).
  How it got there: `docs/android-poc.md`.
- Web upload no longer has “download instead of displaying”. The report always
  opens in the viewer; Save keeps a file, Open in browser opens the HTML
  outside the app.

### Fixed
- Android: the GitHub link at the bottom of the page did nothing. External
  URLs open in the system browser; only loopback stays in the WebView.
- Android: Save used Content-Disposition; the WebView dropped the file. The
  first response is intercepted and a system Save-as dialog is used.
- Desktop GUI: the GitHub footer and Open in browser stayed on 127.0.0.1
  inside the window. They now open in the system browser (report as a temp file).

### Security
- Web jobs are looked up by listing the temp directory, not by joining the
  URL token onto a path.
- Uploads are stored as `upload.zip` / `upload.csv`; zip members are written
  one by one after each path component is checked. The original client
  filename is not used on disk.
- HTTP error text no longer includes raw exception strings or filesystem paths.

## [0.20.0] - 2026-08-28

### Changed
- Android applicationId and namespace are `de.peisenh.loopcrreview`
  (was `com.example.loopcr`). Existing sideload installs must be
  uninstalled once; this is a new app as far as Android is concerned.
  versionCode is 2.
- Android launcher icon uses the report mark (`docs/logo-mark.svg`)
  instead of the hand-drawn placeholder.

## [0.19.0] - 2026-08-28

### Added
- Android app on the release: GitHub Actions builds
  `loop-cr-review-android.apk` and attaches it next to the desktop
  binaries. Same analysis, on-device, sideload only. Local build:
  `./tools/build-android-apk.sh` (JDK 17 + Android SDK).
- Documented where that APK works (4 KB page-size devices) and where it
  does not (16 KB kernels / Play Store).

### Fixed
- Android PoC: choosing an export on a Pixel 8 left "error" under the date
  range. The system file URI never reached Flask. The pick is copied into
  app cache as a real .zip/.csv first.
- Android PoC: after a report, New report / Save sat under the status bar
  and could not be used. Insets go on a wrapper around the WebView; the
  chrome layout no longer assumes a 49 px bar.
- Android PoC: broken logo on the upload page. Sync now copies static/*.svg
  into the APK and Flask serves that folder.

## [0.18.3] - 2026-08-27

### Changed
- The web UI (Docker and the desktop window) shows a finished report in an
  app chrome: New report goes back to the form, Save downloads the same HTML
  the CLI writes. The report file itself is unchanged. Viewing no longer removes
  the job, so a second look or a save still works.
- Since viewing keeps the job, the upload and the unpacked export are deleted as
  soon as the report exists rather than waiting for the sweep — the raw health
  data would otherwise have stayed around long after anything needed it. What is
  left is the report: gone right away with "download" ticked, otherwise with the
  sweep.
- That sweep now also runs on a timer. It used to happen only at start-up and
  before a new upload, so on a machine that is simply left running the TTL never
  came into effect.

### Fixed
- The result routes answered 500 instead of 409 while a report was still being
  built. The helper signalled "not ready" by returning a 2-tuple, while the
  callers told a result apart from a response by asking whether it was a tuple —
  so they unpacked the 409 into three names.
- Save in the desktop window did nothing. pywebview disables downloads unless
  ALLOW_DOWNLOADS is set; Qt WebEngine then shows the normal save dialog for
  the same link the browser already used.
- The privacy note promised the files go as soon as the report has been fetched,
  which stopped being true with the viewer. Both READMEs, the upload page and the
  comment at the top of `webapp.py` now say what actually happens — and say it
  the same way, which is where this kept going wrong.

## [0.18.2] - 2026-08-27

### Fixed
- After downloading a report the form stayed stuck. With "download" ticked the
  browser saves the file and stays on the page, so no navigation ever reset the
  form: the box kept announcing a running analysis and the button stayed
  disabled, leaving no way to start a second report without reloading.
- Choosing a second file in the web form kept the date range of the first one.
  The range is read from the chosen export, but the old values stayed in place
  while the new ones were fetched — and after a failed fetch, or after going
  back in the browser, they stayed for good. The report was then built for a
  period the new export may not cover, and failed. The range is cleared as soon
  as another file is picked, submitting waits until the new one is known, and
  coming back with the browser clears it too.
- A failed analysis said only "could not build report from this export". The
  underlying message is written for the user ("no CGM samples in the chosen
  date range") and is passed on now, as the synchronous path already did.

## [0.18.1] - 2026-08-27

### Fixed
- The web app started a thread per upload with no limit. Each analysis unpacks up
  to 300 MB and holds a whole report in memory, so a handful of parallel uploads
  could run a small home server out of memory. At most two run at once now; the
  rest wait and stay visible as queued.
- The job directory in the shared temp area was created with mode 0700, which only
  helps when we create it. An existing one kept whatever owner and mode it had, so
  someone could put it there first and read the exports afterwards. It is now
  refused when it belongs to another user or is not a directory, and tightened
  when its permissions are too open.
- A slot could be headlined "loop throttles noticeably" while its loop figure was
  positive. The sentence was produced by elimination — a "too strong" verdict that
  did not come from a real drop in the curve was assumed to come from the loop —
  without ever looking at the extra basal. It is only used now when the extra
  basal really is negative; otherwise the headline just says the curve returns
  close to baseline.
- The web app left every abandoned job behind. Cleanup only happened when the
  client fetched the result or polled after the TTL, so a browser tab closed
  right after the upload left the export, the unpacked files and the finished
  report in the temp area for as long as the machine ran. Stale jobs are now
  swept at import and before each new upload; a running job is untouched.
- The privacy note said nothing is kept on the server, which stopped being true
  when the analysis moved into a background job: the upload and the result do
  sit on disk while the report is built. README and upload page say so now,
  together with when they go away.

## [0.18.0] - 2026-08-26

### Changed
- Exports without a basal trace now get the full assessment, not just the curves.
  Everything the glucose alone can say applies to them as well: the return delta,
  the verdict that follows from it, and every derivation from the curve shape.
  Only what genuinely needs a basal trace stays out — the loop extra basal and
  CR_eff, along with the CamAPS-specific passages. Part 2 used to be dropped
  wholesale for these sources although the data for most of it was there. What
  remains is the classic view: this much bolus for this many carbs, and this is
  where glucose stood four hours later — a picture that is arguably cleaner
  without a loop smoothing the excursion.

### Fixed
- A meal the basal trace does not cover was dropped entirely, silently shrinking
  the sample. It now keeps its glucose course and counts towards the verdict;
  only its loop figures stay empty.
- Contamination and hypo rescues were hardcoded as absent for sources without
  basal, although both come from the glucose curve and meal times alone.
- With no meal carrying a bolus the report printed a carb ratio of "1:nan".
- Three loose ends in the live-progress code: an import inside a function and two
  callback parameters that are part of a signature but unused here.

### Fixed
- A real Glooko export was refused on upload. The cap on how many CSVs may be
  opened to look at their headers was set to 12, while a Glooko export holds 18
  (cgm, bolus, basal, alarms, ...) — and the web upload asked the
  content-sniffing readers before checking for Glooko's file names. The cap now
  sits at 40, where it still catches a home directory but no export, and the web
  upload checks Glooko first, as the command line already did.

### Changed
- The readers no longer open files that are none of their business. Glooko and
  Nightscout are recognised by file name alone, so they are checked first: for a
  real Glooko export nothing else is opened at all. Only when neither is present
  do the LibreView and Clarity readers look at headers — and then at most
  4 KB per file, so a CSV without line breaks is no longer read whole.
- Hidden directories and the usual noise (`.git`, `node_modules`, `__pycache__`,
  `.venv`, …) are skipped; an export never hides in them.
- More than a dozen CSV candidates below the given folder are refused with a
  clear message instead of being read one by one: that is not an export folder.

### Added
- Added live progress reporting to the asynchronous web analysis. The progress
  now advances through the actual report-generation phases, including per-day
  progress while the expensive daily charts are rendered. The same progress
  UI is used by the web app and the Windows/Linux desktop GUI.
- Localised all progress/status messages in the web upload UI through the
  existing gettext/Babel catalogs (German and English).
- Added VSCodium project configuration for the repository.

## [0.17.0] - 2026-08-25

### Changed
- **`export_dir` is required now.** Without a folder the tool used to default to
  the working directory and search it recursively — a call in the wrong place
  walked the whole tree and opened every CSV it met to look at the header. It
  prints the usage instead. If you used to run it from inside the export folder,
  pass `.` explicitly.
- **The search stops two levels below the given folder.** That covers every real
  export layout (a Glooko export unpacks into one directory with `Insulin data/`
  under it). An export buried deeper is no longer found.
- **Several exports below one folder are refused.** The tool lists the candidates
  and stops, rather than analysing whichever sorted first — nothing in the report
  said which one it had used. Applies to Nightscout dumps, LibreView and Clarity
  CSVs alike.

The report itself is unchanged: same input, byte-identical output.

## [0.16.0] - 2026-08-25

### Added
- Dexcom Clarity as a data source (`lcr/readers/dexcom.py`). One CSV holding
  glucose, carbs and insulin as separate rows; carbs and insulin only exist when
  they were logged in the Dexcom app, so a glucose-only export is read as such.
  Always lite — Clarity carries no basal rate, so there is no loop-aware part.
  Long-acting insulin is deliberately not counted as a meal bolus: on injections
  it stands in for a basal rate and says nothing about a single meal. The device
  and alert rows at the top of the file are skipped (their thresholds sit in the
  glucose column), and "Low"/"High" become 40/400 rather than being dropped,
  which would look like a sensor gap.
- `parse_ts` accepts the ISO form with a `T` that Clarity writes.
- The web form takes a Clarity CSV as well; its label and hint name the sources
  instead of singling LibreView out.

### Fixed
- `babel.cfg` still only looked at `loop_cr_review.py` and the templates, so every
  string that moved into `lcr/` during the package split was invisible to the
  extraction — 155 of 223 msgids. Nothing broke while the catalogs were left
  alone, but the next `pybabel update` would have dropped two thirds of the
  translations. The config now covers `lcr/**.py` and `webapp.py`.
- Untranslated German strings that surfaced once the extraction was complete
  (TIR targets, TITR label), and a dead line in the web app's export detection.

### Fixed
- `tools/build-binaries.sh` produced a broken Qt GUI without saying so: PyInstaller's
  `--collect-all` only warns when a package is missing, so a build environment without
  the qt extra yielded a binary that dies on start with "No module named 'qtpy'".
  The script now refuses before the build when `qtpy` or `PyQt6` are not importable,
  and the bundle check looks for Qt itself — it had only verified the templates and
  catalogs, which are present either way. Two further traps are checked now: the
  build runs through `python3 -m PyInstaller`, so a `pyinstaller` on the PATH
  belonging to a different interpreter cannot silently bundle the wrong packages,
  and PyQt6 has to be the pip wheel — a distribution package splits the Qt runtime
  across system paths, and the resulting binary aborts on start with
  "base::CommandLine cannot be properly initialized".

## [0.15.0] - 2026-08-25

### Added
- `tools/build-binaries.sh` and `tools/make-screenshots.sh`. The first builds
  the PyInstaller binaries with the release workflow's flags and checks the
  generated report has content — a onefile build can fail over a file that is
  not bundled or an import PyInstaller does not follow, and no unit test sees
  that. It covers the CLI and both GUI variants; since a GUI cannot be started
  without a display, its bundle is read from the archive instead. The second regenerates the README pictures from the example data with
  whichever of chromium/google-chrome is installed, so they stop drifting behind
  the layout.

### Changed
- The 2300-line single module is split into a small package. `lcr/common.py`
  holds i18n, units, errors, method constants and the slot helpers,
  `lcr/charts.py` all matplotlib, and `lcr/readers/` one module per source
  (`glooko.py`, `nightscout.py`, `libreview.py`) with the shared pieces in its
  `__init__` — a fourth source will be a new file rather than edits in a shared
  one. `loop_cr_review.py` keeps the analysis and the rendering and re-exports
  everything, so `webapp`, `gui`, the tests and `sim/` import exactly as before:
  the split is internal, and the generated report is byte-identical.
  The method itself now sits in `lcr/analysis.py`, apart from the rendering, so
  a change to the report cannot quietly change a verdict. `loop_cr_review.py`
  is down from 2300 to 447 lines: the CLI, the context assembly and the
  re-exports.
- Duplication that only became visible once the sources sat in separate modules:
  three copies of the carb-entry merging became one `merge_carb_entries()`, and
  the Glooko basal timeline now uses the same `_basal_from_segments()` as
  Nightscout.
- `tool_version` (reads git / `_version.py`) and `loop_rest` (analysis of
  meal-free windows) had ended up among the readers; both moved to where they
  belong.
- `_libreview_csv` is now the public `libreview_csv` — `webapp` had been
  importing the private name.
- `.pylintrc`: the module-line limit drops from 1750 to 1000, since no module
  needs the raised value any more. The remaining size limits are documented for
  what they are: the reader and context boundaries are wide by nature.

### Fixed
- TIR/GRI card layout and text overflow in PDF print output, and TIR target
  wrapping without changing the HTML layout.
- A stray `@contextmanager`, left behind when a chart helper moved out of the
  shared module, decorated `fmt_cr` instead. Every carb ratio in the report then
  rendered as `<contextlib._GeneratorContextManager object at 0x…>` — and the
  whole suite stayed green, because no test looked at what the cells contain.
  There is one now, plus checks that the numeric cells are numeric.
- A blanket rename of the loop variables `X`/`Y` in the charts also hit a
  strftime format: `%Y` became `%ys`, so every daily panel was titled
  "01.07.26s" instead of "01.07.2026". Only a diff of the generated report
  showed it — the text was identical, the images were not. The panel title is
  covered by a test now.
- The line silencing matplotlib's "building the font cache" message was dropped
  as an unused import while tidying up after the split, so the onefile binary
  printed it on every start again. It sits next to the `MPLCONFIGDIR` setting
  again — both have to run before matplotlib is imported — and both are checked
  by a test.
- Unused imports, two single-letter variable names, a missing docstring and the
  matplotlib configuration sitting between imports.

## [0.14.0] - 2026-08-24

### Added
- Added GRI (Glycemia Risk Index) with grid to report

## [0.13.2] - 2026-08-23

### Fixed
- Cache the CGM timestamp array used for meal-window gap checks to avoid repeated conversion and substantially reduce report generation time for longer reports.
- Vectorized the day-clustered bootstrap in `decision_stability()` while preserving the existing resampling and stability calculation for further time reduction.

### Changed
- `--dark-charts` / UI: dark PNGs for **all** charts only when requested (AGP, slot curves, baseline-norm, daily); default embeds light only (~faster).

## [0.13.1] - 2026-08-23

### Changed
- Slot profiles: `default`, `extended` (05–11/11–15/15–22), `with_snacks` (09–11 and 15–17); CLI `--slots-profile`, web dropdown.
- Baseline-norm panels: slot titles without clock windows; fixed Δ axis −100…+150 (may clip).

## [0.13.0] - 2026-08-22

### Changed
- Baseline-normalised section: one panel per meal slot (2 per row) with median and 10–90 / 25–75 % bands.

### Fixed
- Lite: curve note no longer refers to the Part 2 CR table.
- Lite report title is “AGP & meal windows” (not CR assessment).

## [0.12.1] - 2026-08-21

### Added
- Date range: `--span` / `--from` / `--to`; web fills the full span after choosing a file (second request; nothing kept on the server).

## [0.12.0] - 2026-08-21

### Added
- Nightscout `entries.json` + `treatments.json` import (UTC from dateString/created_at, local clock from CGM utcOffset; Temp Basal as basal). Default is lite (no CR assessment) unless `--assume-camaps` or the upload checkbox.
- LibreView glucose CSV (historic CGM + carbs/insulin). Always lite; no basal, no Part 2.
- Lite mode still shows the per-meal table (time, CHO, bolus, derived CR, Δ) without extra/CR_eff.
- Daily charts without a basal ribbon (CGM + meal marks).

### Changed
- Upload form accepts a ZIP or a LibreView CSV. The CamAPS-assessment checkbox is source-agnostic. Dark-daily label is translated.

### Fixed
- Lite report title is AGP only (no “CR assessment”).
- LibreView uses historic glucose (type 0) only — scans no longer inflate sensor wear above 100 %.
- Nightscout/LibreView lite no longer prints or computes slot verdicts on the CLI.
- Empty-slice warning when a slot has no numeric extra basal.
- LibreView unit taken from the glucose columns, not the ketone mmol/L header (AGP was off-scale).

## [0.11.1] - 2026-08-21

- Dark-theme **daily** charts only with `--dark-charts` / UI checkbox; AGP and slot charts still always have both.
- CGM window lookup by searchsorted (same mean/gap rule).

## [0.11.0] - 2026-08-21

### Added
- `selection_effect()`: per slot, how many meals the verdict actually uses and how
  far that selection would move the normalised curves. Reported in its own section
  of the method part, so the effect of the selection is a number instead of an
  invitation to compare two charts.

- The method part is down from seven blocks to three: the concept box, one block
  holding the CR table together with what follows from it (verdict chips, the
  meal selection and the derived levers), and one block with the explanations and
  limits. Nothing was dropped; stability had been explained twice in the same
  block and is now stated once, and the duplicated heading is gone.
- The fasting basal rate gets its own labelled line next to the time windows,
  with the assumption it rests on, instead of being mentioned in passing inside a
  paragraph and again as a bullet further down. It is the reference every "Loop"
  figure is measured against, so it should not be the easiest thing to miss.
- Screenshots in `docs/` regenerated for the new structure.
- The report is split into two labelled parts and an appendix. **Part 1** shows
  what was recorded — key figures, time in ranges, AGP, the absolute and the
  normalised postprandial courses — with no selection and no assessment.
  **Part 2** holds everything that depends on the method and opens with "How to
  read this report", so the caveats come before the verdicts instead of after
  them. The daily plots stay neutral and move to an **appendix**. Nothing is
  computed differently; the change makes the boundary between measurement and
  interpretation explicit instead of implicit.
- The normalised slot-curve chart now shows **all** meals of a slot, like the
  absolute chart above it, instead of silently switching to the verdict's
  clean-meal selection. Both charts had been drawn from different meal sets
  without that being stated next to the picture.

### Fixed
- Captions that pointed at the wrong place after the reordering: the selection
  note names the normalised curves in Part 1 rather than "the curve above", the
  neutral caption no longer refers forward to a column that only exists in
  Part 2, and the absolute-curve caption no longer claims the normalised curves
  use a different meal selection.

## [0.10.2] - 2026-08-20

### Added
- VALIDATION.md records two more findings from the single real export: the
  signal is a property of the per-slot median, not of individual meals (pooled
  correlation +0.26, absent in two of four slots), and `loop_rest()` classifies
  that export as `active` (131 meal-free stretches, ~499 h, 38 % median
  deviation from the fasting reference). Also notes that extra basal and Δ4h
  share the same glucose curve, so part of their agreement is built in.
- VALIDATION.md gains a real-data counter-check against one 88-day CamAPS FX
  export (aggregates only). The real loop is less neutral than the simulated
  PID — 11.6 % of meal-free windows fall inside the 0.2 U gate and 37.7 % of
  minutes are delivered at zero basal — the 0-4 h integral is shown to mix a
  throttling phase around the meal with a top-up phase from about +3 h, and the
  carb-linked basal response that does exist cannot be attributed to a ratio
  error. Recorded, not acted upon: a later window correlates better with the
  glucose outcome in this one export, which is too thin to move the core
  measure. The conclusion is that the obstacle is identifiability, not
  signal-to-noise.

- README: extra basal may fit a weak CR, is not specific on CamAPS.
- Drop “quiet loop → CR_eff closer to the right CR”.
- Wording: extra basal is Auto Mode activity, not proof of a CR error.
- Rest note is descriptive only (no quiet/active verdict).

## [0.10.1] - 2026-08-20

### Added
- Meal-free rest flag (quiet / active / unclear) vs fasting basal.
  Context for the CR table, not a new estimate.
- Phase B exit: [sim/PHASE_B_ROBUST.md](sim/PHASE_B_ROBUST.md). Same seed
  reproduces; 0 % quiet; +20 % verdict jitters; simulation frozen.
- `sim/robust_check.py` / [sim/PHASE_B_ROBUST.md](sim/PHASE_B_ROBUST.md):
  exit reproducibility check, not a new factorial.
- #002 +20 % noise sweep: 0/5 at σ=0, 2/5 at σ=1, 0/5 at σ=5.
- Stable SHA-256 seeds; `blind_eval --sigmas` prints E and D per slot.
- Noisy blind slice: #002/#010 lunch+dinner 0 % is 10/10 ok; ±20/±30 %
  is 0/40 hit. Phase B gate for this slice fails.
- Seeded CGM noise in `sim.export.run_days`; `blind_eval --noise` / `--seed`.
- [sim/PHASE_B_DESIGN.md](sim/PHASE_B_DESIGN.md): pre-registered blind Phase B
  (0 % FPR first, lunch/dinner, no CamAPS replica).
- Blind runs on four adults: 0 % and ±20 %, documented in
  [sim/UPTAKE.md](sim/UPTAKE.md). `--slots` / several `--patient`.
- `blind_eval --slots` and several `--patient` names; score lunch/dinner only.
- Blind path: `sim/blind_eval.py` + `sim/blind_score.py` (hit/fp),
  `tests/test_blind_score.py`.
- Phase A.8: E0 variance is 63 % gain, 18 % patient. `python3 -m sim.phase_a8`.
- `sim/uptake_mech.py`: off-grid L and hourly extra. Net 4 h L is a
  leftover after a meal-driven first hour, not a set share of D.
- Phase A.5–A.7 on the same CSV: fail is an E0 offset (not a shallower
  L); cluster-bootstrap L̂ 0.25–0.35 on pass; L̂ stable for gates
  0.10–0.30 U.
- Independent simulator under `sim/` (physiology, measured CR_true, CGM-only
  PID, isolation). `phase_a.py` writes the adult grid 10 × 3 × −30…+30 %.
  Dependency only in `requirements-sim.txt`. Summary: [sim/UPTAKE.md](sim/UPTAKE.md).
- Phase A.2: analysis `LOOP_RATIO` (E/bolus > 0.12) on that extra basal.
  At a pass gate, zero CR error stays ok; ±15–20 % is rarely flagged.
  `python3 -m sim.phase_a2`.
- Phase A.3: 21/30 work-points fail the neutrality gate. E0 tracks PID
  gain (weak under, strong over); only adult#002 passes all three gains.
  Behind the gate E ≈ 0.29·D (R²=0.87); on failures R²=0.22. L per
  work-point 0.23–0.53, not universal. `python3 -m sim.phase_a3`.
- Phase A.4: CR_eff vs CR_set as estimators of CR_ref. Behind the gate
  CR_eff is closer in 87 % of rows (mae 10.8 % vs 16.2 %); outside it is
  not. `python3 -m sim.phase_a4`.
- `sim/export.py`: Glooko-style export through the real readers (parse,
  fasting basal, slots). adult#001, 5 days: correct CR → no false alarm,
  CR_eff ~3 % from the measured reference; 25 % too-weak CR → CR_eff
  closes about 45 % of the gap, one slot in three flagged.
- `sim/SIMULATION-SPEC.md`: independent check of the method premise. simglucose
  is MIT.

- Move `SIMULATION-SPEC.md`, `PHASE_B_DESIGN.md`, `PHASE_B_ROBUST.md`
  under `sim/`; update links. Final conclusion in `sim/UPTAKE.md`.
- `sim/phase_a2.py` imports `verdict_class` / `LOOP_RATIO` from the
  analysis instead of restating 0.12.
- `sim/UPTAKE.md` reports L as median 0.33, quartiles 0.24–0.49, range
  −0.19…0.80, names the two negative work-points, and states that the
  asymmetry hypothesis is not confirmed.

## [0.10.0] - 2026-08-19

### Added
- The report now states what the method can actually see, taken from the
  sensitivity measurement rather than left implicit: a carb-ratio error below
  ~15 % stays invisible, from ~25 % it is flagged reliably, and days help mainly
  against false alarms (a correctly set slot is still flagged in ~34 % of cases
  at five days, ~3 % at three weeks). A day count below 10 is marked "(few)" so
  a verdict resting on a short window is visible as such.

### Added
- `tools/validate_sensitivity.py` and a second section in VALIDATION.md: how
  large a carb-ratio error has to be before the verdict rule reacts, measured
  against a known truth. The rule reaches 50/50 at roughly a 15 % error and
  becomes reliable (>90 %) from about 25 %, which follows from the 0.12
  loop-share threshold. More days help mainly against false alarms — a
  correctly set slot is still flagged in a third of runs at five days, in 3 %
  at 21. Outliers, CGM gaps and bolus noise barely change detection but roughly
  double the false alarms. Noise levels are calibrated against real exports.

### Added
- `tools/validate_bootstrap.py` plus [VALIDATION.md](VALIDATION.md): a reproducible
  check of the statistics against a known truth — does the "95 %" day spread
  actually cover the true median, and does decision stability separate a clear
  slot from a borderline one. This is where the day gate comes from (74.9 %
  coverage at 3 days, 88.4 % at 4, 93.9 % at 5). The document also records what
  the check cannot show: the generator draws independent, clean days, so the
  numbers validate the resampling procedure, not the carb-ratio inference on
  real data. Linked from the limitations section of both READMEs.

### Fixed
- Report contrast: the meta line under a verdict used `--gen`, which is 2.9:1 on
  the light card background (WCAG asks 4.5) — it now uses `--muted` (5.3:1). The
  low-stability highlight was a hardcoded colour that dropped to 3.0:1 in dark
  mode; it is now a `--meta-low` variable defined per colour scheme.
- A stray `#, fuzzy` marker in the German catalog made Babel skip one entry, so
  the report showed "loop" instead of "Loop".

- Report UI denser (screen = print): one uncertainty legend; stability and day-spread
  on a single meta line in table and slot cards; shorter curve/CR_eff notes.

### Added
- Slot cards now show the day-to-day spread (2.5th/97.5th percentile over the
  same day-clustered resamples) for the two quantities a reader acts on:
  CR_eff and the loop share. Called "spread across days", not a confidence
  interval — it covers the choice of recorded days only, not the systematic
  confounding by loop adaptation. Nominal CR (a setting, not an estimate) and
  the Δ4h spread (regularly wider than the value itself) are left out. Same
  gates, seed and resampling pass as decision stability, so the extra cost is
  negligible (~0.7 s total for a 14-day export).
- Slots below those gates no longer just stay silent, which looked like a
  defect: they show the plainly observed CR_eff range instead, labelled as
  such ("too few days for a 95 % spread — observed range …"), together with
  the meals and days it rests on. The gate follows the measurement: coverage
  of the spread is driven by the number of days (79 % at 3 days, 85 % at 4,
  ~90 % from 5), so the day gate stays at 5 and the meal gate dropped from 8
  to 5, which no longer excludes slots that are thin in meals but spread over
  enough days.

### Fixed
- A `{% trans %}` block containing a literal percent sign was never translated:
  Jinja escapes it to `%%` in the lookup key while Babel writes a single `%`
  to the catalog, so the two never matched. The percent sign now sits outside
  the translated text.
- The GUI test asserting the desktop launcher binds to loopback only silently
  skipped itself on Debian hosts, where the hostname resolves to 127.0.1.1 —
  so it ran on CI but not on the machines it matters for. It now determines
  the outward address via a UDP socket and actually runs there.

## [0.9.0] - 2026-08-18

### Added
- Optional **decision stability** next to each slot verdict: whole recorded days
  are resampled with replacement and the same verdict rule is re-run, so the
  report states how sensitive a verdict is to which meals happened to be
  recorded. Shown only from 8 meals on 5 separate days (below that the figure
  looks reassuring without carrying information); a verdict that does not
  survive resampling is called out explicitly, as a badge and in the verdict
  text. Fixed seed, so reports stay reproducible. The method box states plainly
  that this is not a statement about whether the carb ratio is correct and not a
  confidence interval. The existing classification is unchanged — the verdict
  rule was extracted into `verdict_class()` and is shared by both paths, so a
  resampled verdict cannot drift from the real one. Shown in the CR table and in
  the slot cards; computed once per slot (~0.6 s for a 14-day export). No new
  dependency (numpy only); catalogs updated for de and en.
- Analysis core tests (`tests/test_analysis_core.py`, 24 cases) with values
  computed by hand: loop extra basal integrated over the window, CR_eff for
  positive/negative/zero extra insulin (including the nan guard when a suspend
  exceeds the bolus), the 4 h delta, contamination windows, the consensus
  metrics (TIR/TAR/TBR/CV/GMI) and the verdict thresholds around LOOP_RATIO
  and D4_HIGH. Verified by mutation: breaking the unit conversion, dropping
  the loop share from CR_eff or shifting the TIR cut-off each make them fail.

- CONTRIBUTING documents the current checks: pylint over all three modules,
  `unittest discover` (so the command does not go stale when a test file is
  added), what each test module covers, the extra dependencies the web/GUI
  tests need, and the expectation that analysis changes come with a
  hand-computed expected value.

### Fixed
- The CR table never showed the "few clean meals" caveat as a badge: the slot
  context did not carry `low_confidence` at all, so the table appended it as
  text to the verdict while the slot cards used a badge and hatched background
  for the same slot. Table and cards now agree; both caveats appear as a badge
  *and* spelled out in the verdict text, which survives copy/paste and print
  where a badge is easy to miss.
- Untranslated German string in the web upload form (the slot field hint).

## [0.8.4] - 2026-08-17
### Added
- Desktop launcher tests (`tests/test_gui.py`, 12 cases): pywebview backend
  selection per platform/build including the `LOOP_CR_GUI` override, the
  local-port helpers, and that the bundled waitress server serves the same
  Flask app on loopback only.
- Dependabot config for pip, GitHub Actions and Docker (weekly, grouped
  minor/patch bumps). The DCO workflows now skip bot commits, which cannot
  carry a Signed-off-by line.
  The CI test job installs the launcher dependencies (waitress, pywebview) and
  the GUI tests skip themselves when those are absent.
- Web front-end regression tests (`tests/test_webapp.py`, 25 cases): upload
  hardening (zip-slip, absolute paths, decompression bombs, entry floods,
  corrupt archives), the three slot sources (built-in / field editor / uploaded
  JSON) including the two bugs fixed below, option validation, the download
  switch and reverse-proxy sub-path awareness. Malformed input is asserted to
  return HTTP 400 rather than 500. CI now discovers all test modules and
  installs Flask so the web suite runs on every push.

- Upload form: Babel i18n (de/en), switchable via language field; default remains German.
- CI: align checkout/setup-python with build-release (v7; Node 20 deprecation warning).
- All internal error and status messages are now consistently English, matching
  the rest of the code base (argparse help, web-layer aborts, docstrings). The
  `LoopCRError` texts and the CLI's success line were the last German holdouts.
  User-facing output (report, upload form) stays fully localised via gettext.
- Code quality back to pylint 10.00/10: explicit exception chaining in
  `load_slots_file`, public `current_translation()` accessor instead of reaching
  into the core's private ContextVar from the web layer, `importlib.util.find_spec`
  instead of a throwaway import when probing for PyQt6, and `.pylintrc` limits
  raised with a rationale for the data-assembly functions and the dark-mode charts.

### Fixed
- The CR table never showed the "few clean meals" caveat as a badge: the slot
  context did not carry `low_confidence` at all, so the table appended it as
  text to the verdict while the slot cards used a badge and hatching for the
  same slot. Table and cards now agree. Both caveats appear as a badge *and*
  spelled out in the verdict text — the wording survives copy/paste and print,
  where a badge is easy to miss.
- Report: the `<html lang>` attribute now follows the selected report language
  instead of being hardcoded to `de` (content was already translated correctly;
  this only affected screen readers and browser language detection).
- Web front-end: invalid slots entered in the field editor returned HTTP 500
  instead of 400 — that path still caught only the legacy `SystemExit` and not
  `LoopCRError`. The uploaded-JSON path was already correct.
- Web front-end: the automatically appended catch-all slot used a hardcoded
  label, so a German report showed the English "Other" for field-editor slots.
  It now uses the same msgid as the built-in slot and is translated normally.

## [0.8.3] - 2026-08-17
- Windows desktop: slim WebView2 build (`loop-cr-review-gui-windows.exe`) plus full Qt
  build (`…-gui-windows-qt.exe`); Linux GUI stays Qt.


## [0.8.2] - 2026-08-17
- Dark mode: upload UI and report follow `prefers-color-scheme`; report print stays light;
  charts embed light+dark PNGs in the same HTML file.
- Clean-meal selection: exclude meals with a CGM gap > 25 min in the post-meal
  window when at least 3 gap-free clean meals exist (fallback: all meals).
- README (de/en) and web upload: short privacy / homelab notes (self-hosted only, no public hosting).
- Unittest + Babel workflow on every push/PR (.github and .gitea, mirrored).
- Report limitations: note that CamAPS Boost/Ease-off are not in the Glooko CSV export and can
  distort CR signals when active (manual awareness only).
- Analysis state (slots, language, glucose unit) uses ContextVars so concurrent
  web/GUI requests do not leak configuration across threads.


## [0.8.1] - 2026-08-16
- Report presentation: clearer CR column headers —
  ``CR (CHO/bolus)`` vs ``CR_eff (+loop)`` — and an explicit note that both are
  derived from the export, not the pump’s programmed ICR.
- Short method box near the top of the HTML report (CamAPS scope, loop
  extra-basal formula, two ratios, discussion-only use).
- Absolute postprandial curve: short note that it uses all meals per slot, while the CR table and baseline-normalised curves use the clean-meal rule (so n/shape may differ by design).
- Interpretation legend tags aligned with table verdict wording (too strong → loosen / too weak → tighten / plausibly adequate).
- Low-confidence slots: clearer hatching, dashed outline, and a “low confidence” tag in the CR table and derivation cards; legend notes the hatched row.
- Web upload UI: explicit CamAPS FX (Auto Mode) only notice; README lead-in points to the supported-systems section.


## [0.8.0] - 2026-08-16
### Added
- Desktop app (`gui.py`): runs the web front-end in a native window via
  pywebview + Qt (PyQt6 WebEngine), backed by a local waitress server —
  a double-click binary with no browser, no Docker, localhost only.
  Pre-built binaries for Windows and Linux are built in CI and attached
  to releases; `requirements-gui.txt` covers a run from source.
  Reuses the same templates, reports and analysis as the CLI/web.
  Note: binaries are larger (\~250–280 MB) because the Qt WebEngine is bundled.
- `example-data/Alex_Beispiel_Glooko_export.zip`: Glooko-style ZIP of the
  synthetic demo export (CSV files only) so the web front-end upload path
  can be tested without packaging the folder by hand.
- Automated regression tests (`tests/test_example_data.py`) against the
  synthetic example export: parsers, slot JSON, demo slot verdicts
  (breakfast strong / lunch weak / dinner ok), English report, and ZIP
  extract ≡ folder analysis. Run with `python3 -m unittest tests.test_example_data -v`.

- Analysis core raises :class:`LoopCRError` instead of calling ``sys.exit``
  for invalid slots, unreadable slot files and missing basal data; the CLI
  maps that to exit code 1 and the web front-end to HTTP 400.
- ``generate_report`` installs custom slots only inside a scoped context
  (``_slot_scope``) and restores the built-in ``DEFAULT_SLOTS`` afterwards,
  so concurrent GUI/web requests do not leak slot configuration via module
  globals.
- ``select_slot_rows()`` is the single rule for which meals feed a slot's
  median table/verdict and the baseline-normalised curves (prefer
  contamination-free rows, fall back to all if fewer than
  ``MIN_CLEAN_MEALS``). Behaviour unchanged; absolute median curves still
  use every meal in the slot by design.

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

[Unreleased]: https://github.com/peisenh/loop-cr-review/compare/v0.23.0...HEAD
[0.23.0]: https://github.com/peisenh/loop-cr-review/compare/v0.22.0...v0.23.0
[0.22.0]: https://github.com/peisenh/loop-cr-review/compare/v0.21.0...v0.22.0
[0.21.0]: https://github.com/peisenh/loop-cr-review/compare/v0.20.1...v0.21.0
[0.20.1]: https://github.com/peisenh/loop-cr-review/compare/v0.20.0...v0.20.1
[0.20.0]: https://github.com/peisenh/loop-cr-review/compare/v0.19.0...v0.20.0
[0.19.0]: https://github.com/peisenh/loop-cr-review/compare/v0.18.3...v0.19.0
[0.18.3]: https://github.com/peisenh/loop-cr-review/compare/v0.18.2...v0.18.3
[0.18.2]: https://github.com/peisenh/loop-cr-review/compare/v0.18.1...v0.18.2
[0.18.1]: https://github.com/peisenh/loop-cr-review/compare/v0.18.0...v0.18.1
[0.18.0]: https://github.com/peisenh/loop-cr-review/compare/v0.17.0...v0.18.0
[0.17.0]: https://github.com/peisenh/loop-cr-review/compare/v0.16.0...v0.17.0
[0.16.0]: https://github.com/peisenh/loop-cr-review/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/peisenh/loop-cr-review/compare/v0.14.0...v0.15.0
[0.14.0]: https://github.com/peisenh/loop-cr-review/compare/v0.13.2...v0.14.0
[0.13.2]: https://github.com/peisenh/loop-cr-review/compare/v0.13.1...v0.13.2
[0.13.1]: https://github.com/peisenh/loop-cr-review/compare/v0.13.0...v0.13.1
[0.13.0]: https://github.com/peisenh/loop-cr-review/compare/v0.12.1...v0.13.0
[0.12.1]: https://github.com/peisenh/loop-cr-review/compare/v0.12.0...v0.12.1
[0.12.0]: https://github.com/peisenh/loop-cr-review/compare/v0.11.1...v0.12.0
[0.11.1]: https://github.com/peisenh/loop-cr-review/compare/v0.11.0...v0.11.1
[0.11.0]: https://github.com/peisenh/loop-cr-review/compare/v0.10.2...v0.11.0
[0.10.2]: https://github.com/peisenh/loop-cr-review/compare/v0.10.1...v0.10.2
[0.10.1]: https://github.com/peisenh/loop-cr-review/compare/v0.10.0...v0.10.1
[0.10.0]: https://github.com/peisenh/loop-cr-review/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/peisenh/loop-cr-review/compare/v0.8.4...v0.9.0
[0.8.4]: https://github.com/peisenh/loop-cr-review/compare/v0.8.3...v0.8.4
[0.8.3]: https://github.com/peisenh/loop-cr-review/compare/v0.8.2...v0.8.3
[0.8.2]: https://github.com/peisenh/loop-cr-review/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/peisenh/loop-cr-review/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/peisenh/loop-cr-review/compare/v0.7.0...v0.8.0
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
