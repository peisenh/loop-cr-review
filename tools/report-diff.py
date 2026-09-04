#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Peter Eisenhauer
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prove a change did not move a single number in the report.

The numpy removal touches the arithmetic behind every figure, so the check
cannot be "looks about right": the report has to come out identical. Anything
else means a rank, a rounding or a comparison shifted.

Two lines legitimately differ between any two runs — the generation timestamp
and the version string, which carries `-dirty` while a working tree has
uncommitted changes. Those are blanked before comparing; everything else must
match to the character.

Usage:
    tools/report-diff.py --save          # before the change
    tools/report-diff.py                 # after it
"""
from __future__ import annotations

import argparse
import difflib
import pathlib
import re
import sys

# Runs from tools/, so the project itself is one directory up.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

REF_DIR = pathlib.Path("/tmp/report-ref")
# Both parts of the generation line: version-with-describe, and the timestamp.
NOISE = (
    re.compile(r'v\d+\.\d+\.\d+[-\w.]*'),
    re.compile(r'\d{2}\.\d{2}\.\d{4}, \d{2}:\d{2}'),
)
# The unit is detected from the export, not chosen here, so both languages with
# and without the daily overview is the whole surface a report can have.
CASES = (
    ("de", {"lang": "de"}),
    ("de_daily", {"lang": "de", "daily": True}),
    ("en", {"lang": "en"}),
    ("en_daily", {"lang": "en", "daily": True}),
)


def normalise(html):
    """-> the report with the two run-dependent parts blanked"""
    for pattern in NOISE:
        html = pattern.sub("X", html)
    return html


def build(export, case):
    """-> (name, normalised report) for one case"""
    import loop_cr_review as core        # pylint: disable=import-outside-toplevel
    name, kwargs = case
    html, _ctx = core.generate_report(export, **kwargs)
    return name, normalise(html)


def main():
    """-> exit code"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", action="store_true",
                        help="write the current reports as the reference")
    parser.add_argument("--export", default="example-data")
    args = parser.parse_args()

    REF_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0
    for case in CASES:
        try:
            name, html = build(args.export, (case[0], dict(case[1])))
        except Exception as exc:                    # pylint: disable=broad-except
            print(f"  {case[0]:<10} could not be built: {exc}")
            failures += 1
            continue
        path = REF_DIR / f"{name}.html"
        if args.save:
            path.write_text(html, encoding="utf-8")
            print(f"  {name:<10} saved, {len(html)} characters")
            continue
        if not path.exists():
            print(f"  {name:<10} no reference — run with --save first")
            failures += 1
            continue
        reference = path.read_text(encoding="utf-8")
        if reference == html:
            print(f"  {name:<10} identical")
            continue
        failures += 1
        print(f"  {name:<10} DIFFERS")
        diff = difflib.unified_diff(reference.split("\n"), html.split("\n"),
                                    lineterm="", n=0)
        for line in list(diff)[:12]:
            print(f"    {line[:110]}")
    if args.save:
        return 0
    print("  ->", "nothing moved" if not failures else f"{failures} case(s) to look at")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
