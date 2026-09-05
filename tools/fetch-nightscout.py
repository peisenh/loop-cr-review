#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Peter Eisenhauer
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pull entries and treatments from a Nightscout site into a folder to analyse.

The Nightscout reader wants `entries.json` and `treatments.json` side by side.
This writes exactly those, so the folder can go straight into the tool — or be
zipped and dropped on the upload page.

Why not one big request: the API answers with the ten most recent values from
the last two days unless told otherwise, and a `count` large enough for three
months is the kind of query that times out on a small instance. So it walks the
range in windows and stitches the results together, dropping anything that comes
back twice at a boundary.

Authentication is by access token — the kind Nightscout's admin page creates for
a role, which can be revoked on its own and given read rights alone:

    --token READ-TOKEN

Not needed if the site reads without authentication. The older API_SECRET is not
supported on purpose: the protocol wants it as a SHA-1 hash sent with every
request, which is both a weak hash and a credential that cannot be revoked
without changing it everywhere. A token is the better answer and every current
Nightscout has them.

Usage:
    tools/fetch-nightscout.py --url https://mysite.example --token abc123 --days 90
    tools/fetch-nightscout.py --url ... --from 2026-06-01 --to 2026-09-01 -o data/ns
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# One window per week. Small enough that a modest instance answers, large enough
# that ninety days is a dozen requests rather than ninety.
WINDOW_DAYS = 7
# Well above a week of five-minute readings (about 2 000), so the window bound
# is what limits the answer rather than this.
PAGE_COUNT = 20000
TIMEOUT = 120


def _fetch(url, params):
    """One API call. -> parsed JSON list"""
    query = urllib.parse.urlencode(params, safe="[]$")
    request = urllib.request.Request(f"{url}?{query}")
    request.add_header("Accept", "application/json")
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def _windows(start, end):
    """The range split into WINDOW_DAYS pieces. -> list of (from, to)"""
    out, cursor = [], start
    while cursor < end:
        step = min(cursor + timedelta(days=WINDOW_DAYS), end)
        out.append((cursor, step))
        cursor = step
    return out


def _collect(base, path, field, start, end, token, label):
    """Every record in the range, in order, without duplicates. -> list"""
    url = f"{base}/api/v1/{path}"
    seen, out = set(), []
    for window_start, window_end in _windows(start, end):
        params = {
            "count": PAGE_COUNT,
            f"find[{field}][$gte]": window_start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            f"find[{field}][$lt]": window_end.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        if token:
            params["token"] = token
        try:
            batch = _fetch(url, params)
        except urllib.error.HTTPError as error:
            hint = ""
            if error.code in (401, 403):
                hint = "  (the site wants a token, or this one has no read rights)"
            raise SystemExit(f"{label}: {error.code} {error.reason}{hint}") from error
        except urllib.error.URLError as error:
            raise SystemExit(f"{label}: cannot reach {base} — {error.reason}") from error

        fresh = 0
        for record in batch:
            # _id is unique per record; without it a boundary would duplicate.
            key = record.get("_id") or json.dumps(record, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            out.append(record)
            fresh += 1
        print(f"  {label}: {window_start:%d.%m.} – {window_end:%d.%m.}  "
              f"{len(batch):>6} gelesen, {fresh:>6} neu")
    return out


def main():
    """-> exit code"""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True,
                        help="base URL of the site, e.g. https://mysite.example")
    parser.add_argument("--token", help="read access token")
    parser.add_argument("--days", type=int, default=90,
                        help="how far back to go, when --from is not given (default 90)")
    parser.add_argument("--from", dest="date_from", help="first day, YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", help="last day, YYYY-MM-DD (exclusive)")
    parser.add_argument("-o", "--out", default="nightscout-export",
                        help="folder to write into (default nightscout-export)")
    args = parser.parse_args()

    end = (datetime.strptime(args.date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
           if args.date_to else datetime.now(timezone.utc))
    start = (datetime.strptime(args.date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
             if args.date_from else end - timedelta(days=args.days))
    if start >= end:
        raise SystemExit("the start of the range is not before its end")

    base = args.url.rstrip("/")
    print(f"==> {base}  {start:%d.%m.%Y} bis {end:%d.%m.%Y}")
    entries = _collect(base, "entries.json", "dateString", start, end,
                       args.token, "entries")
    treatments = _collect(base, "treatments.json", "created_at", start, end,
                          args.token, "treatments")

    if not entries:
        raise SystemExit("no glucose readings in that range — check the dates and the site")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, data in (("entries.json", entries), ("treatments.json", treatments)):
        path = out / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(f"==> {path}  {len(data)} Einträge, {path.stat().st_size / 1048576:.1f} MB")

    print(f"\n    ./loop_cr_review.py {out} -d")
    return 0


if __name__ == "__main__":
    sys.exit(main())
