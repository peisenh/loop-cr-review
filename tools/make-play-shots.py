#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Peter Eisenhauer
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Store screenshots: the real page at phone size, cut where a section starts.

Taking them by hand on a device means redoing every one whenever a heading or a
wording changes. Cutting single cards out instead looked worse than the hand-made
ones — an isolated card on empty background is not what the app shows.

So the whole page is rendered as it is, and each picture starts where a chosen
section starts. Finding that point needs no guessed pixel offsets: an invisible
marker line in a colour nothing else uses goes in front of each section, the page
is measured once at scale 1, and the marker's row in that image is the offset to
render at.

Usage:  make-play-shots.py <page.html> <out-dir> <name:heading> [...]
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

BROWSERS = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
# What a Pixel 8 actually reports to a page: 412x915 CSS at 2.62x, giving
# 1080x2400 — the same file size as a screenshot taken on the device. Smaller
# frames fitted noticeably less on screen and looked coarse next to the
# hand-made ones.
WIDTH_CSS = 412
HEIGHT_CSS = 915
SCALE = 2.6214
MEASURE_HEIGHT = 9000      # tall enough for a whole report at scale 1
MARK = (254, 0, 254)       # a magenta the report never uses


def browser():
    """The first chromium/chrome on PATH."""
    for name in BROWSERS:
        if subprocess.run(["which", name], capture_output=True,
                          check=False).returncode == 0:
            return name
    raise SystemExit("No chromium/google-chrome found.")


def shoot(exe, source, out, width, height, scale):
    """One headless screenshot. -> Path"""
    subprocess.run(
        [exe, "--headless", "--disable-gpu", "--hide-scrollbars",
         f"--force-device-scale-factor={scale}",
         f"--window-size={width},{height}",
         "--virtual-time-budget=5000", f"--screenshot={out}", source],
        capture_output=True, check=False)
    if not Path(out).exists() or Path(out).stat().st_size == 0:
        raise SystemExit(f"Screenshot {out} stayed empty")
    return Path(out)


def mark_sections(html, headings):
    """Put a marker line in front of each section. -> (html, missing)"""
    missing = []
    # Back to front, so the earlier positions stay valid while inserting.
    for index, (_name, heading) in reversed(list(enumerate(headings))):
        hit = html.find(heading)
        start = html.rfind('<div class="card', 0, hit) if hit >= 0 else -1
        if start < 0:
            missing.append(heading)
            continue
        marker = (f'<div data-shot="{index}" style="height:1px;background:'
                  f'rgb{MARK};margin:0;padding:0"></div>')
        html = html[:start] + marker + html[start:]
    return html, list(reversed(missing))


def marker_rows(image):
    """Row of every marker line, top to bottom. -> list[int]"""
    pixels = image.convert("RGB").load()
    rows, width = [], image.width
    for y in range(image.height):
        # The marker spans the content column; three samples are enough.
        if all(pixels[x, y] == MARK for x in (width // 4, width // 2, 3 * width // 4)):
            if not rows or y - rows[-1] > 2:
                rows.append(y)
    return rows


def main():
    """-> exit code"""
    if len(sys.argv) < 4:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    source, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    headings = [arg.split(":", 1) for arg in sys.argv[3:]]
    out_dir.mkdir(parents=True, exist_ok=True)
    exe = browser()

    html = source.read_text(encoding="utf-8")
    marked, missing = mark_sections(html, headings)
    if missing:
        print("Not found in the page — headings changed?", file=sys.stderr)
        for item in missing:
            print(f"  {item!r}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        marked_page = work / "marked.html"
        marked_page.write_text(marked, encoding="utf-8")

        # Measure once at scale 1: cheap, and offsets come out in CSS pixels.
        measured = shoot(exe, f"file://{marked_page}", work / "measure.png",
                         WIDTH_CSS, MEASURE_HEIGHT, 1)
        with Image.open(measured) as image:
            offsets = marker_rows(image)
        if len(offsets) != len(headings):
            print(f"Found {len(offsets)} markers for {len(headings)} sections — "
                  f"is the page taller than {MEASURE_HEIGHT} px?", file=sys.stderr)
            return 1

        for (name, _heading), offset in zip(headings, offsets):
            # Scroll by pulling the body up, then shoot a single viewport.
            # Pull the body up to scroll, and make every marker invisible —
            # they keep their 1px height so the offsets stay valid, but a
            # magenta line through the picture is not what anyone wants to see.
            shifted = marked.replace(
                "</head>",
                f"<style>body{{margin-top:-{offset + 1}px}}"
                f"[data-shot]{{background:transparent!important}}</style></head>", 1)
            shifted_page = work / f"{name}.html"
            shifted_page.write_text(shifted, encoding="utf-8")
            target = out_dir / f"{name}.png"
            shoot(exe, f"file://{shifted_page}", target, WIDTH_CSS, HEIGHT_CSS, SCALE)
            print(f"    {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
