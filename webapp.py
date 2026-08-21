"""Minimal homelab web front-end for loop-cr-review.

Wraps the reusable :func:`loop_cr_review.generate_report` core in a small
Flask app: upload a CamAPS/Glooko export ZIP, pick a few options, get the
HTML report back. Intended for private LAN use, not public hosting.

Health data is handled in a temporary directory and deleted immediately
after the report is built (ephemeral: nothing is stored, nothing is logged).
"""
import os
import tempfile
import zipfile
from pathlib import Path

from flask import Flask, request, render_template, abort, Response
from jinja2 import select_autoescape
from werkzeug.middleware.proxy_fix import ProxyFix

import loop_cr_review as core
from loop_cr_review import LoopCRError

REPO = "https://github.com/peisenh/loop-cr-review"
MAX_UPLOAD_BYTES = 64 * 1024 * 1024        # 64 MB cap for the (compressed) ZIP
MAX_ENTRIES = 5000                         # refuse archives with absurd file counts
MAX_FILE_BYTES = 100 * 1024 * 1024         # 100 MB per extracted file
MAX_TOTAL_BYTES = 300 * 1024 * 1024        # 300 MB total uncompressed (zip-bomb guard)

app = Flask(__name__)
app.jinja_env.add_extension("jinja2.ext.i18n")
app.jinja_env.autoescape = select_autoescape(["html", "htm", "xml", "j2"])
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
# Honour X-Forwarded-* from a trusted reverse proxy (Traefik in the homelab):
# X-Forwarded-Prefix lets the app run under a sub-path (e.g. /loop-cr-review)
# so url_for() generates correct links; Proto/Host keep HTTPS redirects right.
# Direct LAN access without these headers is unaffected.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


def _safe_extract(zf, dest):
    """Extract a ZIP into dest, guarding against path- and size-based abuse.

    Rejects (HTTP 400): members escaping dest (zip-slip / absolute paths /
    symlinks), too many entries, and archives whose declared uncompressed size
    exceeds the per-file or total caps (decompression bomb). Sizes come from the
    central directory, which is enough to stop the practical bombs before any
    bytes are written to disk.
    """
    dest = dest.resolve()
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        abort(400, "archive has too many entries")
    total = 0
    for info in infos:
        target = (dest / info.filename).resolve()
        if target != dest and not str(target).startswith(str(dest) + os.sep):
            abort(400, "unsafe path in archive")
        if info.file_size > MAX_FILE_BYTES:
            abort(400, "a file in the archive is too large")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            abort(400, "archive expands to too much data")
    zf.extractall(dest)


def _find_export_base(root):
    """Return the export base folder, or abort(400) if none is found.

    The readers expect a folder that holds cgm_data_*.csv directly and an
    "Insulin data" subfolder alongside it (bolus/basal live there). Prefer a
    candidate that has both; fall back to the first cgm_data parent so a
    CGM-only export still gets a clear downstream error rather than a 404.
    """
    ns = [p.parent for p in Path(root).rglob("entries.json")
          if (p.parent / "treatments.json").is_file()]
    if ns:
        return ns[0]
    candidates = [cgm.parent for cgm in Path(root).rglob("cgm_data_*.csv")]
    lv = [p.parent for p in Path(root).rglob("*.csv")]
    # LibreView: parent of a CSV with Record Type / Aufzeichnungstyp
    from loop_cr_review import _libreview_csv
    lv = _libreview_csv(root)
    if lv:
        return lv.parent
    if not candidates:
        abort(400, "no cgm_data_*.csv, Nightscout dump or LibreView CSV found")
    for parent in candidates:
        if (parent / "Insulin data").is_dir():
            return parent
    return candidates[0]


def _read_options():
    """Validate and return (lang, window_hours, daily, dark_charts) from the form."""
    lang = _ui_lang()
    try:
        window_hours = float(request.form.get("window_hours", "4"))
    except ValueError:
        abort(400, "invalid window value")
    if not 0.5 <= window_hours <= 12:
        abort(400, "window must be between 0.5 and 12 hours")
    daily = request.form.get("daily") == "on"
    dark_charts = request.form.get("dark_charts") == "on"
    assume_camaps = request.form.get("assume_camaps") == "on"
    return lang, window_hours, daily, dark_charts, assume_camaps


def _slots_from_fields():
    """Build a validated slots list from the repeated label/start/end fields.

    The catch-all ("other") slot is appended automatically. Returns None when
    no rows were filled in (caller then falls back to the built-in slots).
    """
    labels = request.form.getlist("slot_label")
    starts = request.form.getlist("slot_start")
    ends = request.form.getlist("slot_end")
    raw = []
    for i, (label, start, end) in enumerate(zip(labels, starts, ends)):
        if not label.strip():
            continue
        try:
            raw.append({"key": f"s{i + 1}", "label": label.strip(),
                        "start": int(start), "end": int(end)})
        except (TypeError, ValueError):
            abort(400, f"slot '{label}': start/end must be whole numbers")
    if not raw:
        return None
    # Same msgid as the core's built-in catch-all, so the report catalog
    # translates it like any other slot label.
    raw.append({"key": "other", "label": "Other", "start": -1, "end": -1})
    try:
        return core.build_slots(raw, "Slots")
    except (LoopCRError, SystemExit) as exc:  # core raises LoopCRError (legacy SystemExit)
        abort(400, f"invalid slots: {exc}")
    return None                          # pragma: no cover


def _read_slots(tmpd):
    """Resolve the slots choice: default / field editor / uploaded JSON."""
    mode = request.form.get("slots_mode", "default")
    if mode == "fields":
        return _slots_from_fields()
    if mode == "json":
        slots_up = request.files.get("slots")
        if slots_up is not None and slots_up.filename:
            slots_path = tmpd / "slots.json"
            slots_up.save(slots_path)
            return _load_slots_or_400(slots_path)
    return None



def _ui_lang():
    """Language for the upload form and the report (default ``de``)."""
    lang = (request.args.get("lang") or request.form.get("lang") or "de").strip().lower()
    return lang if lang in ("de", "en") else "de"


def _install_ui_i18n(lang):
    """Load gettext catalogs for Jinja ``{% trans %}`` on the upload page."""
    core.setup_i18n(lang)
    app.jinja_env.install_gettext_translations(core.current_translation(), newstyle=True)  # pylint: disable=no-member


@app.route("/", methods=["GET"])
def index():
    """Show the upload form (UI language via ?lang=, default German)."""
    lang = _ui_lang()
    _install_ui_i18n(lang)
    if lang == "de":
        slot_defaults = [["Frühstück", 5, 10], ["Mittag", 11, 15], ["Abend", 17, 22]]
    else:
        slot_defaults = [["Breakfast", 5, 10], ["Lunch", 11, 15], ["Dinner", 17, 22]]
    return render_template(
        "upload.html.j2",
        repo=REPO,
        version=core.tool_version(),
        lang=lang,
        slot_defaults=slot_defaults,
    )


@app.route("/report", methods=["POST"])
def report():
    """Build the report from the uploaded export and return it as HTML."""
    upload = request.files.get("export")
    if upload is None or upload.filename == "":
        abort(400, "no export file uploaded")
    lang, window_hours, daily, dark_charts, assume_camaps = _read_options()

    with tempfile.TemporaryDirectory(prefix="lcr-") as tmp:
        tmpd = Path(tmp)
        extract = tmpd / "export"
        extract.mkdir()
        name = Path(upload.filename or "export").name
        suffix = Path(name).suffix.lower()
        saved = tmpd / name
        upload.save(saved)
        if suffix == ".csv":
            saved.replace(extract / name)
        else:
            try:
                with zipfile.ZipFile(saved) as zf:
                    _safe_extract(zf, extract)
            except zipfile.BadZipFile:
                abort(400, "upload a ZIP (Glooko/Nightscout) or a LibreView CSV")

        slots = _read_slots(tmpd)
        base = _find_export_base(extract)
        html = _generate_or_400(base, lang, window_hours, daily, dark_charts, assume_camaps, slots)

    headers = {}
    if request.form.get("download") == "on":
        headers["Content-Disposition"] = 'attachment; filename="loop-cr-review.html"'
    return Response(html, mimetype="text/html", headers=headers)


def _load_slots_or_400(path):
    """Load a slots file, turning the core's LoopCRError into HTTP 400."""
    try:
        return core.load_slots_file(str(path))
    except (LoopCRError, SystemExit) as exc:  # core raises LoopCRError (legacy SystemExit)
        abort(400, f"invalid slots file: {exc}")
    return None                          # pragma: no cover


def _generate_or_400(base, lang, window_hours, daily, dark_charts, assume_camaps, slots):
    """Run generate_report; map any failure to a clean HTTP 400.

    The analysis core signals input problems in several ways (LoopCRError,
    FileNotFoundError, csv.Error, UnicodeDecodeError, ...). At the request
    boundary we turn all of them into a 400 with a short, generic message so a
    malformed export never crashes a worker or leaks a traceback/temp path.
    """
    try:
        html, _ctx = core.generate_report(
            base, lang=lang, window_hours=window_hours, daily=daily,
            dark_charts=dark_charts, assume_camaps=assume_camaps, slots=slots)
        return html
    except (LoopCRError, SystemExit) as exc:  # core raises LoopCRError (legacy SystemExit)
        abort(400, f"could not build report: {exc}")
    except Exception:                         # pylint: disable=broad-exception-caught
        abort(400, "could not build report from this export "
                   "(unrecognised or corrupt data)")
    return ""                                 # pragma: no cover


if __name__ == "__main__":
    # Dev server only; in the homelab run behind gunicorn (see Dockerfile).
    app.run(host="127.0.0.1", port=8000)
