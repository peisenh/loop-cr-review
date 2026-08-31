#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rebuild Lite example dumps from the synthetic Glooko Alex-Beispiel export.

Reads example-data (folder or Alex_Beispiel_Glooko_export.zip) and writes:

  example-data/nightscout/entries.json + treatments.json
  example-data/libreview/Alex_Beispiel_LibreView.csv
  example-data/clarity/Alex_Beispiel_Clarity.csv

No live patient data. Same invented name, same timestamps as the Glooko demo.
Basal is not copied: those three sources stay Lite on purpose.
"""
from __future__ import annotations

import argparse
import csv
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

NAME = "Alex Beispiel"
# Demo clock is local CEST (UTC+2) in July 2026.
UTC_OFFSET_MIN = 120
DEVICE_CGM = "FreeStyle Libre 3"
DEVICE_PUMP = "mylife YpsoPump"


def _num(cell: str) -> float:
    text = (cell or "").strip().replace(" ", "")
    if not text:
        raise ValueError("empty number")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    return float(text)


def _parse_glooko_ts(cell: str) -> datetime:
    return datetime.strptime(cell.strip(), "%d.%m.%Y %H:%M")


def _read_glooko(src: Path) -> tuple[list[tuple[datetime, float]], list[tuple[datetime, float, float]]]:
    """Return (cgm rows, meal rows as time/cho/insulin)."""
    if src.is_file() and src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as zf:
            names = zf.namelist()
            cgm_name = next(n for n in names if Path(n).name.startswith("cgm_data"))
            bolus_name = next(n for n in names if "bolus_data" in n.replace("\\", "/"))
            cgm_text = zf.read(cgm_name).decode("utf-8-sig")
            bolus_text = zf.read(bolus_name).decode("utf-8-sig")
    else:
        cgm_files = sorted(src.glob("cgm_data_*.csv"))
        bolus_files = sorted((src / "Insulin data").glob("bolus_data_*.csv")) if (src / "Insulin data").is_dir() else []
        if not cgm_files or not bolus_files:
            raise SystemExit(f"no Glooko CGM/bolus CSV under {src}")
        cgm_text = cgm_files[0].read_text(encoding="utf-8-sig")
        bolus_text = bolus_files[0].read_text(encoding="utf-8-sig")

    cgm: list[tuple[datetime, float]] = []
    rows = list(csv.reader(cgm_text.splitlines()))
    for row in rows[2:]:
        if len(row) < 2 or not row[0].strip():
            continue
        cgm.append((_parse_glooko_ts(row[0]), _num(row[1])))

    meals: list[tuple[datetime, float, float]] = []
    rows = list(csv.reader(bolus_text.splitlines()))
    for row in rows[2:]:
        if len(row) < 6 or not row[0].strip():
            continue
        cho = _num(row[3]) if row[3].strip() else 0.0
        ins = _num(row[5]) if row[5].strip() else 0.0
        if cho <= 0 and ins <= 0:
            continue
        meals.append((_parse_glooko_ts(row[0]), cho, ins))
    return cgm, meals


def _as_utc(local: datetime) -> datetime:
    tz = timezone(timedelta(minutes=UTC_OFFSET_MIN))
    return local.replace(tzinfo=tz).astimezone(timezone.utc)


def write_nightscout(dest: Path, cgm, meals) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    entries = []
    for ts, sgv in cgm:
        utc = _as_utc(ts)
        entries.append({
            "type": "sgv",
            "sgv": int(round(sgv)),
            "date": int(utc.timestamp() * 1000),
            "dateString": utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "utcOffset": UTC_OFFSET_MIN,
            "device": f"synthetic {DEVICE_CGM}",
        })
    treatments = []
    for ts, cho, ins in meals:
        utc = _as_utc(ts)
        treatments.append({
            "eventType": "Meal Bolus",
            "created_at": utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "carbs": round(cho, 2),
            "insulin": round(ins, 3),
            "notes": "synthetic example, not a patient",
        })
    (dest / "entries.json").write_text(
        json.dumps(entries, indent=0) + "\n", encoding="utf-8")
    (dest / "treatments.json").write_text(
        json.dumps(treatments, indent=2) + "\n", encoding="utf-8")


def write_libreview(path: Path, cgm, meals) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "Gerät", "Gerätezeitstempel", "Aufzeichnungstyp",
        "Glukosewert-Verlauf mg/dL", "Glukose-Scan mg/dL",
        "Schnellwirkendes Insulin (Einheiten)",
        "Kohlenhydrate (Gramm)",
    ]
    lines = [
        f"Patientenname,{NAME},Synthetisch,kein Echtdatensatz",
        ",".join(header),
    ]

    def stamp(ts: datetime) -> str:
        return ts.strftime("%d-%m-%Y %H:%M")

    for ts, sgv in cgm:
        lines.append(",".join([
            DEVICE_CGM, stamp(ts), "0", f"{sgv:.0f}", "", "", "",
        ]))
    for ts, cho, ins in meals:
        if ins > 0:
            lines.append(",".join([
                DEVICE_CGM, stamp(ts), "4", "", "", f"{ins:.2f}".replace(".", ","), "",
            ]))
        if cho > 0:
            lines.append(",".join([
                DEVICE_CGM, stamp(ts), "5", "", "", "", f"{cho:.0f}",
            ]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def write_clarity(path: Path, cgm, meals) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "Index", "Event Type", "Event Subtype", "Patient Info", "Device Info",
        "Source Device ID", "Glucose Value (mg/dL)", "Insulin Value (u)",
        "Carb Value (grams)", "Duration (hh:mm:ss)", "Glucose Rate of Change (mg/dL/min)",
        "Transmitter Time (Long Integer)", "Timestamp",
    ]
    rows = [
        {"Index": "1", "Event Type": "FirstName", "Patient Info": "Alex"},
        {"Index": "2", "Event Type": "LastName", "Patient Info": "Beispiel"},
        {"Index": "3", "Event Type": "Device", "Device Info": f"synthetic {DEVICE_CGM}"},
    ]
    idx = 4
    t0 = cgm[0][0] if cgm else datetime(2026, 7, 1)
    for ts, sgv in cgm:
        tx = int((ts - t0).total_seconds())
        rows.append({
            "Index": str(idx),
            "Event Type": "EGV",
            "Glucose Value (mg/dL)": f"{sgv:.0f}",
            "Transmitter Time (Long Integer)": str(tx),
            "Timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        idx += 1
    for ts, cho, ins in meals:
        tx = int((ts - t0).total_seconds())
        stamp = ts.strftime("%Y-%m-%dT%H:%M:%S")
        if cho > 0:
            rows.append({
                "Index": str(idx),
                "Event Type": "Carbs",
                "Carb Value (grams)": f"{cho:.0f}",
                "Transmitter Time (Long Integer)": str(tx),
                "Timestamp": stamp,
            })
            idx += 1
        if ins > 0:
            rows.append({
                "Index": str(idx),
                "Event Type": "Insulin",
                "Event Subtype": "FastActing",
                "Insulin Value (u)": f"{ins:.3f}",
                "Transmitter Time (Long Integer)": str(tx),
                "Timestamp": stamp,
            })
            idx += 1
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=None,
        help="Glooko folder or Alex_Beispiel_Glooko_export.zip "
             "(default: example-data next to this repo)",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="example-data directory to write into (default: same tree as --source)",
    )
    args = parser.parse_args()
    here = Path(__file__).resolve()
    repo = here.parents[1] if here.parent.name == "tools" else Path.cwd()
    source = args.source
    if source is None:
        zipped = repo / "example-data" / "Alex_Beispiel_Glooko_export.zip"
        folder = repo / "example-data"
        source = zipped if zipped.is_file() else folder
    out = args.out or (
        source.parent if source.is_file() else source
    )
    if not source.exists():
        raise SystemExit(f"source not found: {source}")

    cgm, meals = _read_glooko(source)
    if not cgm:
        raise SystemExit("no CGM rows in Glooko source")
    write_nightscout(out / "nightscout", cgm, meals)
    write_libreview(out / "libreview" / "Alex_Beispiel_LibreView.csv", cgm, meals)
    write_clarity(out / "clarity" / "Alex_Beispiel_Clarity.csv", cgm, meals)
    print(f"cgm={len(cgm)} meals={len(meals)}")
    print(f"wrote {out / 'nightscout'}")
    print(f"wrote {out / 'libreview'}")
    print(f"wrote {out / 'clarity'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
