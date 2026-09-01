#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Peter Eisenhauer
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Make a screenshot fit for the Play Store, and say so if it cannot.

A headless browser writes PNGs with an alpha channel, and the store rejects
those outright. Flattening onto white is all it takes — but a rejected upload
gives no hint about which rule was broken, so the rest is checked here too.

Usage:  check-play-shot.py <png> [...]
"""
import sys
from pathlib import Path

from PIL import Image

# From Google's own asset requirements: each side 320-3840 px, the longer side
# at most twice the shorter, JPEG or 24-bit PNG without alpha, up to 8 MB.
MIN_SIDE = 320
MAX_SIDE = 3840
# Google documents "no more than twice as long", but a plain 1080x2400 phone
# screenshot is 2.22:1 and sits in the store accepted. Kept a little above the
# documented figure so a device-sized shot passes; a genuinely odd shape still
# gets caught.
MAX_RATIO = 2.4
MAX_BYTES = 8 * 1024 * 1024


def fix_and_check(path):
    """Flatten *path* onto white and check it. -> list of complaints."""
    with Image.open(path) as image:
        if image.mode in ("RGBA", "LA", "P"):
            flat = Image.new("RGB", image.size, "white")
            rgba = image.convert("RGBA")
            flat.paste(rgba, mask=rgba.split()[-1])
            flat.save(path, "PNG")
            image = flat
        width, height = image.size
        mode = image.mode

    problems = []
    if mode != "RGB":
        problems.append(f"mode is {mode}, the store wants 24-bit RGB")
    short, long_ = sorted((width, height))
    if short < MIN_SIDE:
        problems.append(f"{width}x{height}: shorter side below {MIN_SIDE} px")
    if long_ > MAX_SIDE:
        problems.append(f"{width}x{height}: longer side above {MAX_SIDE} px")
    if long_ > MAX_RATIO * short:
        problems.append(f"{width}x{height}: ratio {long_ / short:.2f}:1 exceeds "
                        f"{MAX_RATIO:.1f}:1")
    size = Path(path).stat().st_size
    if size > MAX_BYTES:
        problems.append(f"{size / 1e6:.1f} MB is over the 8 MB limit")
    return problems, f"{width}x{height}"


def main():
    """-> exit code."""
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    failed = False
    for name in sys.argv[1:]:
        problems, size = fix_and_check(name)
        if problems:
            failed = True
            print(f"    {name}  {size}  REJECTED", file=sys.stderr)
            for problem in problems:
                print(f"      {problem}", file=sys.stderr)
        else:
            print(f"    {name}  {size}  ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
