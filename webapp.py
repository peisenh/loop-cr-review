"""Minimal homelab web front-end for loop-cr-review.

Wraps the reusable :func:`loop_cr_review.generate_report` core in a small
Flask app: upload a CamAPS/Glooko export ZIP, pick a few options, get the
HTML report back. Intended for private LAN use, not public hosting.

Health data is handled in a temporary directory and deleted immediately
after the report is built (ephemeral: nothing is stored, nothing is logged).
"""
import json
import os
import re
import tempfile
import stat
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path

from flask import Flask, request, render_template, abort, Response, jsonify
from jinja2 import select_autoescape
from werkzeug.middleware.proxy_fix import ProxyFix

import loop_cr_review as core
from loop_cr_review import LoopCRError, dexcom_csv, libreview_csv

REPO = "https://github.com/peisenh/loop-cr-review"
MAX_UPLOAD_BYTES = 64 * 1024 * 1024        # 64 MB cap for the (compressed) ZIP
MAX_ENTRIES = 5000                         # refuse archives with absurd file counts
MAX_FILE_BYTES = 100 * 1024 * 1024         # 100 MB per extracted file
MAX_TOTAL_BYTES = 300 * 1024 * 1024        # 300 MB total uncompressed (zip-bomb guard)

# Async analysis jobs are short-lived and live only in the system temp area.
# The upload and the unpacked export go as soon as the report exists. What is
# left - the report itself - is removed when it is handed over as a direct
# download, and otherwise by the TTL sweep, which also runs on a timer. Viewing
# in the app chrome deliberately keeps the report, so Save and a second look work.
JOB_TTL = 15 * 60
_JOB_ROOT = Path(tempfile.gettempdir()) / "loop-cr-review-jobs"
_JOB_LOCK = threading.Lock()
# At most this many analyses run at once. Each one unpacks up to MAX_TOTAL_BYTES
# and holds a full report in memory, so an unbounded thread per upload is an easy
# way to run a small home server out of memory.
MAX_CONCURRENT_JOBS = 2
_JOB_SLOTS = threading.Semaphore(MAX_CONCURRENT_JOBS)


def _prepare_job_root():
    """Create the job directory, and refuse a pre-existing one we do not own.

    The temp area is shared. Creating it with mode 0o700 only helps when we
    create it: an existing directory keeps whatever owner and mode it has, so
    someone could put it there first and read the exports afterwards.
    """
    try:
        _JOB_ROOT.mkdir(mode=0o700)
        return
    except FileExistsError:
        pass
    info = _JOB_ROOT.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise RuntimeError(f"{_JOB_ROOT} exists and is not a directory")
    if info.st_uid != os.getuid():
        raise RuntimeError(f"{_JOB_ROOT} belongs to another user - refusing to use it")
    if info.st_mode & 0o077:
        _JOB_ROOT.chmod(0o700)


_prepare_job_root()

app = Flask(__name__)
app.jinja_env.add_extension("jinja2.ext.i18n")
app.jinja_env.autoescape = select_autoescape(["html", "htm", "xml", "j2"])
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
# Honour X-Forwarded-* from a trusted reverse proxy (Traefik in the homelab):
# X-Forwarded-Prefix lets the app run under a sub-path (e.g. /loop-cr-review)
# so url_for() generates correct links; Proto/Host keep HTTPS redirects right.
# Direct LAN access without these headers is unaffected.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)



def _client_message(exc, fallback):
    """User-facing LoopCRError text, never a filesystem path or traceback."""
    raw = exc.args[0] if exc.args else fallback
    if not isinstance(raw, str) or not raw.strip():
        return fallback
    if "/" in raw or "\\" in raw or "Traceback" in raw:
        return fallback
    return raw

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
    planned = []
    part_ok = re.compile(r"^[\w .()+\-\[\]]{1,200}$", re.UNICODE)
    for info in infos:
        if info.file_size > MAX_FILE_BYTES:
            abort(400, "a file in the archive is too large")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            abort(400, "archive expands to too much data")
        rel = info.filename.replace("\\", "/")
        raw_parts = [p for p in rel.split("/") if p not in ("", ".")]
        if not raw_parts:
            continue
        parts = []
        for raw in raw_parts:
            matched = part_ok.fullmatch(raw)
            if matched is None or raw == "..":
                abort(400, "unsafe path in archive")
            parts.append(matched.group(0))
        target = dest.joinpath(*parts).resolve()
        if target != dest and not str(target).startswith(str(dest) + os.sep):
            abort(400, "unsafe path in archive")
        planned.append((info, target, rel.endswith("/")))
    for info, target, is_dir in planned:
        if is_dir or info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info, "r") as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out, length=1024 * 1024)


def _unpack_upload(tmpd, upload):
    """Save the upload into tmpd/export and return that folder. No keep after tmpd dies.

    On disk the file is always upload.zip or upload.csv.
    """
    extract = tmpd / "export"
    extract.mkdir()
    raw = Path(upload.filename or "export").name
    suffix = Path(raw).suffix.lower()
    if suffix == ".csv":
        saved = tmpd / "upload.csv"
        upload.save(saved)
        saved.replace(extract / "upload.csv")
    elif suffix in (".zip", ""):
        saved = tmpd / "upload.zip"
        upload.save(saved)
        try:
            with zipfile.ZipFile(saved) as zf:
                _safe_extract(zf, extract)
        except zipfile.BadZipFile:
            abort(400, "upload a ZIP (Glooko/Nightscout) or a LibreView/Dexcom Clarity CSV")
    else:
        abort(400, "upload a ZIP (Glooko/Nightscout) or a LibreView/Dexcom Clarity CSV")
    return extract


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
    # Glooko is recognised by file name, so it comes first: the readers below open
    # files to look at their headers, and there is no reason to do that for an
    # export we have already identified.
    if not candidates:
        # LibreView: a CSV with Record Type / Aufzeichnungstyp.
        # Dexcom Clarity: a CSV with Event Type / Transmitter Time.
        for finder in (libreview_csv, dexcom_csv):
            found = finder(root)
            if found:
                return found.parent
        abort(400, "no cgm_data_*.csv, Nightscout dump, LibreView or Dexcom Clarity CSV found")
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
    date_from = request.form.get("date_from") or None
    date_to = request.form.get("date_to") or None
    try:
        date_from = core.parse_day(date_from)
        date_to = core.parse_day(date_to)
    except LoopCRError as exc:
        abort(400, _client_message(exc, "invalid date"))
    return lang, window_hours, daily, dark_charts, assume_camaps, date_from, date_to


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
    """Resolve slots: built-in profile / field editor / uploaded JSON."""
    mode = request.form.get("slots_mode", "default")
    if mode == "fields":
        return _slots_from_fields()
    if mode == "json":
        slots_up = request.files.get("slots")
        if slots_up is not None and slots_up.filename:
            slots_path = tmpd / "slots.json"
            slots_up.save(slots_path)
            return _load_slots_or_400(slots_path)
    if mode in core.SLOT_PROFILES and mode != "default":
        return core.slots_from_profile(mode)
    return None



def _ui_lang():
    """Language for the upload form and the report (default ``de``)."""
    lang = (request.args.get("lang") or request.form.get("lang") or "de").strip().lower()
    return lang if lang in ("de", "en") else "de"


def _install_ui_i18n(lang):
    """Load gettext catalogs for Jinja ``{% trans %}`` on the upload page."""
    core.setup_i18n(lang)
    app.jinja_env.install_gettext_translations(core.current_translation(), newstyle=True)  # pylint: disable=no-member



def _job_paths(job_id):
    """Return the private directory and status/result paths for a job id.

    The directory object comes from listing _JOB_ROOT, not from joining the
    route parameter onto the filesystem. The URL value is only compared to
    names we already created (uuid4 hex).
    """
    if not job_id or len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        abort(404)
    for job in _JOB_ROOT.iterdir():
        if job.is_dir() and job.name == job_id:
            return job, job / "status.json", job / "result.html"
    abort(404)


def _write_job(status_path, **values):
    """Atomically update a job status JSON file."""
    tmp = status_path.with_suffix(".tmp")
    data = dict(values)
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(status_path)


def _job_progress(status_path, stage, percent):
    """Progress callback used by the analysis core."""
    _write_job(status_path, state="running", stage=stage, percent=int(percent))


def _cleanup_job(job):
    """Remove all temporary input/result data for a completed job."""
    shutil.rmtree(job, ignore_errors=True)


def _sweep_stale_jobs():
    """Drop job directories older than the TTL.

    A browser that is closed after the upload never fetches the result, and
    nothing else would ever remove it: the upload, the unpacked export and the
    finished report would stay in the temp area for as long as the machine runs.
    Called at start-up and before every new job, which is often enough without a
    background thread.
    """
    cutoff = time.time() - JOB_TTL
    with _JOB_LOCK:
        for job in _JOB_ROOT.iterdir():
            if not job.is_dir():
                continue
            try:
                if job.stat().st_mtime < cutoff:
                    shutil.rmtree(job, ignore_errors=True)
            except OSError:
                continue


def _run_job(_job, status_path, result_path, options):
    """Run one analysis job outside the HTTP request thread.

    The job directory comes with the thread arguments but is not needed here;
    the paths below already point inside it.
    """
    with _JOB_SLOTS:
        _do_job(status_path, result_path, options)


def _drop_raw_input(job, keep):
    """Remove everything in *job* except the files named in *keep*."""
    for entry in job.iterdir():
        if entry.name in keep:
            continue
        try:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink()
        except OSError:
            continue


def _sweep_forever(interval=60):
    """Run the sweep on a timer.

    Without it the TTL only bites when something else happens - a new upload, or
    a restart. On a machine that is simply left running, an abandoned job would
    stay for as long as nobody uses the tool again.
    """
    while True:
        time.sleep(interval)
        try:
            _sweep_stale_jobs()
        except Exception:  # pylint: disable=broad-exception-caught
            continue


def _do_job(status_path, result_path, options):
    """The analysis itself, once a slot is free."""
    try:
        _job_progress(status_path, "analysis", 1)
        html, _ctx = core.generate_report(
            options["base"], lang=options["lang"], window_hours=options["window_hours"],
            daily=options["daily"], dark_charts=options["dark_charts"],
            assume_camaps=options["assume_camaps"], date_from=options["date_from"],
            date_to=options["date_to"], slots=options["slots"],
            progress=lambda stage, pct: _job_progress(status_path, stage, pct))
        result_path.write_text(html, encoding="utf-8")
        # The upload and the unpacked export are the health data; the report is
        # derived from them. Once it exists they serve no purpose, and since
        # viewing no longer removes the job, they would otherwise sit here until
        # the TTL sweep.
        _drop_raw_input(status_path.parent, keep={status_path.name, result_path.name})
        _write_job(status_path, state="done", stage="done", percent=100,
                   download=options["download"], lang=options["lang"])
    except (LoopCRError, SystemExit) as exc:
        # LoopCRError carries a message written for the person in front of the
        # browser ("no CGM samples in the chosen date range"). Replacing it with a
        # generic line leaves them guessing; the synchronous path passes it on too.
        _write_job(status_path, state="error", stage="error", percent=100,
                   error=_client_message(exc, "could not build report"))
    except Exception:  # pylint: disable=broad-exception-caught
        _write_job(status_path, state="error", stage="error", percent=100,
                   error="could not build report from this export "
                         "(unrecognised or corrupt data)")


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


@app.route("/span", methods=["POST"])
def span():
    """Return CGM from/to/days for the upload, then drop the temp dir."""
    upload = request.files.get("export")
    if upload is None or upload.filename == "":
        abort(400, "no export file uploaded")
    with tempfile.TemporaryDirectory(prefix="lcr-") as tmp:
        extract = _unpack_upload(Path(tmp), upload)
        base = _find_export_base(extract)
        try:
            info = core.peek_span(base)
        except LoopCRError as exc:
            return jsonify(error=_client_message(exc, "could not read span")), 400
        except FileNotFoundError:
            return jsonify(error="could not read span"), 400
        return jsonify(info)



@app.route("/analyze", methods=["POST"])
def analyze():
    """Start an asynchronous report job and return its opaque job id."""
    upload = request.files.get("export")
    if upload is None or upload.filename == "":
        abort(400, "no export file uploaded")
    lang, window_hours, daily, dark_charts, assume_camaps, date_from, date_to = _read_options()
    _sweep_stale_jobs()
    job_id = uuid.uuid4().hex
    job = _JOB_ROOT / job_id
    job.mkdir(mode=0o700)
    status_path = job / "status.json"
    result_path = job / "result.html"
    try:
        slots = _read_slots(job)
        extract = _unpack_upload(job, upload)
        base = _find_export_base(extract)
        options = {
            "base": str(base), "lang": lang, "window_hours": window_hours,
            "daily": daily, "dark_charts": dark_charts, "assume_camaps": assume_camaps,
            "date_from": date_from, "date_to": date_to, "slots": slots,
            "download": request.form.get("download") == "on",
        }
        _write_job(status_path, state="queued", stage="queued", percent=0)
        threading.Thread(target=_run_job,
                         args=(job, status_path, result_path, options),
                         daemon=True).start()
        return jsonify(job_id=job_id)
    except Exception:
        _cleanup_job(job)
        raise


@app.route("/progress/<job_id>", methods=["GET"])
def progress(job_id):
    """Return the current state of an asynchronous analysis job."""
    job, status_path, _result_path = _job_paths(job_id)
    if not status_path.is_file():
        abort(404)
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        abort(404)
    # Do not retain completed/error jobs forever. A caller can still fetch a
    # completed result immediately; cleanup is handled by /result.
    if data.get("state") in ("done", "error") and time.time() - status_path.stat().st_mtime > JOB_TTL:
        _cleanup_job(job)
        abort(404)
    return jsonify(data)


def _finished_report(job_id):
    """(job dir, status dict, report HTML) for a completed job.

    None while it is still running; aborts for anything worse.
    """
    job, status_path, result_path = _job_paths(job_id)
    if not status_path.is_file():
        abort(404)
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        abort(404)
    if data.get("state") == "error":
        _cleanup_job(job)
        abort(400, data.get("error", "could not build report"))
    if data.get("state") != "done" or not result_path.is_file():
        # None, not a response: the 409 case used to come back as a 2-tuple, and
        # the callers - which check isinstance(..., tuple) - then unpacked it
        # into three names and turned "not ready" into a 500.
        return None
    html = result_path.read_text(encoding="utf-8")
    return job, data, html


@app.route("/result/<job_id>", methods=["GET"])
def result(job_id):
    """Show the report in the app chrome, or attach it when download was ticked.

    The generated HTML is not modified. Looking at it does not delete the job:
    Save and a second look still work until the TTL sweep.
    """
    finished = _finished_report(job_id)
    if finished is None:
        return jsonify(error="report not ready"), 409
    job, data, html = finished
    if data.get("download"):
        _cleanup_job(job)
        return Response(html, mimetype="text/html", headers={
            "Content-Disposition": 'attachment; filename="loop-cr-review.html"',
        })
    lang = data.get("lang") or _ui_lang()
    _install_ui_i18n(lang)
    return render_template("viewer.html.j2", lang=lang, job_id=job_id)


@app.route("/result/<job_id>/body", methods=["GET"])
def result_body(job_id):
    """Unchanged report HTML for the viewer iframe."""
    finished = _finished_report(job_id)
    if finished is None:
        return jsonify(error="report not ready"), 409
    _job, _data, html = finished
    return Response(html, mimetype="text/html")


@app.route("/result/<job_id>/print", methods=["GET"])
def result_print(job_id):
    """Same HTML as the body; Android intercepts this and opens the system printer."""
    return result_body(job_id)


@app.route("/result/<job_id>/external", methods=["GET"])
def result_external(job_id):
    """Bare report HTML for a real browser tab (desktop GUI / optional Android)."""
    finished = _finished_report(job_id)
    if finished is None:
        return jsonify(error="report not ready"), 409
    _job, _data, html = finished
    return Response(html, mimetype="text/html")


@app.route("/result/<job_id>/download", methods=["GET"])
def result_download(job_id):
    """Same file the CLI writes; no app chrome."""
    finished = _finished_report(job_id)
    if finished is None:
        return jsonify(error="report not ready"), 409
    _job, _data, html = finished
    return Response(html, mimetype="text/html", headers={
        "Content-Disposition": 'attachment; filename="loop-cr-review.html"',
    })


@app.route("/report", methods=["POST"])

def report():

    """Build the report from the uploaded export and return it as HTML."""
    upload = request.files.get("export")
    if upload is None or upload.filename == "":
        abort(400, "no export file uploaded")
    lang, window_hours, daily, dark_charts, assume_camaps, date_from, date_to = _read_options()

    with tempfile.TemporaryDirectory(prefix="lcr-") as tmp:
        tmpd = Path(tmp)
        extract = _unpack_upload(tmpd, upload)
        slots = _read_slots(tmpd)
        base = _find_export_base(extract)
        html = _generate_or_400(base, lang, window_hours, daily, dark_charts,
                                assume_camaps, date_from, date_to, slots)

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


def _generate_or_400(base, lang, window_hours, daily, dark_charts, assume_camaps,
                     date_from, date_to, slots):
    """Run generate_report; map any failure to a clean HTTP 400.

    The analysis core signals input problems in several ways (LoopCRError,
    FileNotFoundError, csv.Error, UnicodeDecodeError, ...). At the request
    boundary we turn all of them into a 400 with a short, generic message so a
    malformed export never crashes a worker or leaks a traceback/temp path.
    """
    try:
        html, _ctx = core.generate_report(
            base, lang=lang, window_hours=window_hours, daily=daily,
            dark_charts=dark_charts, assume_camaps=assume_camaps,
            date_from=date_from, date_to=date_to, slots=slots)
        return html
    except (LoopCRError, SystemExit) as exc:  # core raises LoopCRError (legacy SystemExit)
        abort(400, f"could not build report: {exc}")
    except Exception:                         # pylint: disable=broad-exception-caught
        abort(400, "could not build report from this export "
                   "(unrecognised or corrupt data)")
    return ""                                 # pragma: no cover


# Anything left from an earlier run is stale by definition: sweep once at import,
# so a restart cleans up after a crash as well.
_sweep_stale_jobs()
threading.Thread(target=_sweep_forever, daemon=True).start()


if __name__ == "__main__":
    # Dev server only; in the homelab run behind gunicorn (see Dockerfile).
    app.run(host="127.0.0.1", port=8000)
