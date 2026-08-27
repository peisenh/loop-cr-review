# Browser build (Pyodide) — proof of concept

**Status: not pursued.** It works, but it does not do the thing it was built for.

## What was asked

Something to download that then runs locally — on a phone, without a server and
without an app store.

## What was built

The analysis compiled to WebAssembly: `index.html` loads a Pyodide runtime, the
unchanged Python code and the wheels for numpy, matplotlib and jinja2, then runs
`generate_report()` in the browser tab. `browser_entry.py` is the only piece of
browser-specific Python — it takes the bytes of one upload, unpacks them into
the virtual filesystem, finds the export and returns the report HTML.

    ./poc/browser-pyodide/build.sh          # -> dist/browser-pyodide/
    python3 -m unittest discover -s poc/browser-pyodide -p "test_*.py"

## What it showed

Positive, and more clearly than expected:

- The analysis runs **unchanged**. No port, no second implementation.
- The generated report is **text-identical** to the desktop one. Only the chart
  rasterisation differs, as it does between any two matplotlib builds.
- One report from a 14-day Glooko export: **2.5 s** after the runtime is up.
- The bundle is **26 MB unpacked, 19 MB zipped** — the runtime plus 13 wheels,
  not the full Pyodide distribution of 350 MB.
- Versions available in Pyodide 314.0.6: Python 3.14.2, numpy 2.4.6,
  matplotlib 3.10.8, jinja2 3.1.6.

## Why it was dropped

Browsers refuse to load WebAssembly from a `file://` path. The folder therefore
has to be served over HTTP — any static server will do, and it executes nothing
itself, but it has to be there.

That removes the one advantage the approach was chosen for. "Download it and it
runs" is exactly what a browser will not do here. On a phone without a server
there is no way to open it at all.

For that goal an embedded runtime is the honest answer: an app that brings its
own Python, which is what the Chaquopy proof of concept does on Android.

## What it is still good for

If the report is served anyway — a home server, a machine on the local network —
this build moves the analysis off the server and into the browser. The export is
never uploaded; the server only hands out files and never sees health data. That
is a stronger privacy position than the Flask web app, and the code for it is
here and working.

Kept for that reason, and because the measurements above answer a question that
would otherwise have to be asked again.
