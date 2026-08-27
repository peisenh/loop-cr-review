# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Entry point for the browser build: bytes in, report HTML out.

The analysis is the same code as everywhere else. All this module does is what
the web app does before it: put the upload somewhere the readers can open it,
find the export folder inside, and hand back the finished HTML. Nothing is sent
anywhere - the file never leaves the browser tab.
"""
import io
import shutil
import zipfile
from pathlib import Path

import loop_cr_review as core

WORK = Path("/work")
# Same zip-bomb guard as the web app: a small archive can unpack to gigabytes,
# and in a browser tab that means a dead machine rather than a failed request.
MAX_TOTAL_BYTES = 300 * 1024 * 1024
MAX_MEMBERS = 2000


def _safe_extract(archive, dest):
    """Unpack *archive* below *dest*, refusing paths that escape it."""
    total = 0
    for info in archive.infolist()[:MAX_MEMBERS]:
        name = info.filename
        if name.endswith("/"):
            continue
        target = (dest / name).resolve()
        if not str(target).startswith(str(dest.resolve())):
            raise core.LoopCRError(f"refusing path outside the archive: {name}")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise core.LoopCRError("archive unpacks to more than 300 MB")
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)


def _export_base(root):
    """The folder the readers should be pointed at."""
    candidates = [p.parent for p in core.find_below(root, "cgm_data_*.csv")]
    for parent in candidates:
        if (parent / "Insulin data").is_dir():
            return parent
    if candidates:
        return candidates[0]
    for finder in (core.libreview_csv, core.dexcom_csv):
        found = finder(root)
        if found:
            return found.parent
    if (root / "entries.json").is_file():
        return root
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        if (sub / "entries.json").is_file():
            return sub
    raise core.LoopCRError(
        "no Glooko, Nightscout, LibreView or Dexcom Clarity export found in this file")


def build_report(data, filename, lang="de", window_hours=4.0, daily=False,
                 assume_camaps=False):
    """Report HTML from the bytes of one upload. -> str"""
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    payload = bytes(data)

    if filename.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                _safe_extract(archive, WORK)
        except zipfile.BadZipFile as exc:
            raise core.LoopCRError("this does not look like a ZIP file") from exc
    else:
        (WORK / Path(filename).name).write_bytes(payload)

    html, _ctx = core.generate_report(
        str(_export_base(WORK)), lang=lang, window_hours=window_hours,
        daily=daily, assume_camaps=assume_camaps)
    # The unpacked export is health data; it has no reason to outlive the report.
    shutil.rmtree(WORK, ignore_errors=True)
    return html
