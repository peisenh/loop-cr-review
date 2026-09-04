<!-- SPDX-FileCopyrightText: 2026 Peter Eisenhauer -->
<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

# Reporting a security problem

Please do **not** open a public issue for anything security related. Use GitHub's
private reporting instead:

> Repository → **Security** → **Report a vulnerability**

That opens a thread only you and the maintainer can read.

## Do not attach real export data

Reports are health data. Whatever the bug, it can be described without one:

- Use the synthetic files in [`example-data/`](example-data/) — they cover
  Glooko/CamAPS, LibreView, Dexcom Clarity and Nightscout.
- If the problem only shows with a particular file, describe its structure
  (which columns, which rows, what is unusual about it) rather than sending it.
- Crash output often carries values from the file. Trim it before pasting.

If real data was already sent somewhere, say so in the report; that is worth
knowing and is not held against anyone.

## What helps

- The version. The CLI prints it with `--version`, the report has it in the
  footer, the Android app shows it in the menu.
- Where it happens: Android app, desktop window, Docker web app, or command line.
- What an attacker would gain. A crash on malformed input is a bug; a crash that
  reads a file outside the export folder is a vulnerability.
- Steps that reproduce it, ideally with a file from `example-data/`.

## In scope

- The local HTTP server used by the Android app and the desktop window: reaching
  it from another app or another process on the machine, getting past the access
  token, reading a report that belongs to someone else.
- Handling of untrusted archives and CSV/JSON files: paths that escape the
  extraction folder, resource exhaustion, anything that touches the filesystem
  outside the working directory.
- The Android app: exported components, the WebView, what the FileProvider hands
  out, data left behind after the app closes.
- The report itself: input from an export rendered into HTML in a way that
  executes when the report is opened.
- The Docker web app, run as documented — on a private network, for one person.

## Out of scope

- **The analysis being wrong.** If a verdict or a figure is incorrect, that is a
  regular issue, and a welcome one — but it is not a vulnerability.
- **Running the web app on the public internet.** It is not built for that: no
  authentication between users, no multi-tenancy, no rate limiting. Exposing it
  is out of scope rather than a finding.
- **Third-party components** (Chaquopy, numpy, Flask, …). Report
  those upstream. Do tell us if a known one is exploitable *through* this
  software — the wheel versions are pinned here and can be moved.

## Supported versions

Only the latest release. This is a spare-time project; there are no backports to
older versions.

## What to expect

An acknowledgement within a few days, and an honest answer about whether and
when it will be fixed. There is no bounty. Credit in the changelog if you want
it, silence if you prefer.
