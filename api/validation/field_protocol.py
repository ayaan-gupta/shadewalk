"""Write the on-site protocol and the blank measurement sheet for the same 20 segments.

    python -m validation.field_protocol          # writes docs/field-validation.md and validation/field_template.csv
    python -m validation.field_protocol sheet.csv  # scores a filled-in sheet against the model
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from . import independent

ROOT = Path(__file__).resolve().parents[2]
SHEET = ROOT / "api" / "validation" / "field_template.csv"
DOC = ROOT / "docs" / "field-validation.md"
COLUMNS = ["segment_id", "street", "start_lat", "start_lon", "end_lat", "end_lon", "length_m", "model_pct", "date", "time_start", "sky", "shaded_m", "walked_m", "notes"]


def write() -> None:
    result = independent.run(7, 15)
    rows = result["segments"]
    with open(SHEET, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for r in rows:
            writer.writerow([r["segment_id"], r["street"] or "", r["start"][1], r["start"][0], r["end"][1], r["end"][0], r["length_m"], r["model_pct"], "", "", "", "", "", ""])
    table = "\n".join(
        f"| {r['segment_id']} | {r['street'] or 'unnamed path'} | {r['kind']} | {r['length_m']:.0f} | {r['start'][1]:.5f}, {r['start'][0]:.5f} | {r['end'][1]:.5f}, {r['end'][0]:.5f} | {r['model_pct']:.0f}% | {r['check_pct']:.0f}% |"
        for r in rows
    )
    DOC.write_text(f"""# Field validation protocol

The PRD asks for hand-checked shade fractions at 20 sampled segments that agree with the model within 15 percentage points. That needs a person on the street in Dallas at the right hour, which this build could not do. What exists today is an independent computational check on these same 20 segments (see `api/validation/independent.py`). This page is the protocol for the real thing, so it can be done later without redesigning anything.

## When

- A clear day within ten days of 15 July. The table uses 15 July as July's representative day. Across 5 to 25 July the 3 PM sun stays within 4 degrees of azimuth and 1 degree of elevation of that day (pvlib: azimuth 248.2 on the 5th, 244.8 on the 15th, 240.7 on the 25th).
- Measure each segment between 2:50 PM and 3:10 PM Central Daylight Time. The model value is for 3:00 PM exactly, and the sun does not wait: from 2:40 to 3:20 it swings from azimuth 237 to 251 and drops from 71 to 64 degrees, which is too much for a fair comparison.
- Skip the day if cloud covers the sun for more than a moment. Note the sky on the sheet.

## What to bring

A measuring wheel or a 30 m tape, the sheet (`api/validation/field_template.csv`, printed or on a phone), and a camera.

## At each segment

1. Find the start and end coordinates below. Segments are sidewalk or path centre lines between two junctions.
2. Walk the centre line from start to end with the wheel. Record the total as `walked_m`.
3. Walk it again and add up every stretch where your feet are in shade from a building or a tree: `shaded_m`. Shade from a parked truck, an awning or a person does not count, because the model cannot know about it. Under a tree crown or a building overhang counts.
4. Dappled shade: count a stretch as shaded when more than half the ground in it is dark.
5. Photograph the segment from the start point, looking along it.
6. Write down anything the model could not know: scaffolding, a new building, a tree that is gone.

A segment takes about four minutes, so one person covers four or five in the twenty minute window. Plan on four people for one afternoon, or one person across four or five clear days.

## Scoring

`measured_pct = 100 * shaded_m / walked_m`. A segment passes when it is within 15 points of `model_pct`. Run

```
cd api && ../.venv/bin/python -m validation.field_protocol path/to/filled_sheet.csv
```

to get the per-segment differences and the pass count.

## The 20 segments

Model values are the committed shade table for July at 3 PM, trees and buildings. The check column is the independent computation, shown so a surprising field reading can be compared against both.

| id | street | kind | length (m) | start (lat, lon) | end (lat, lon) | model | check |
|---|---|---|---|---|---|---|---|
{table}

Sampling: seeded (`{independent.SEED}`), segments of at least {independent.MIN_LENGTH_M:.0f} m, seven from the sunny end of the table (under 20%), seven from the middle and six from the shady end (60% and over), so that agreement is tested across the range and not only where everything is in full sun.
""")
    print(f"wrote {DOC.relative_to(ROOT)} and {SHEET.relative_to(ROOT)}")


def score(path: Path) -> None:
    rows = [r for r in csv.DictReader(open(path)) if r.get("shaded_m") and r.get("walked_m")]
    if not rows:
        raise SystemExit("no rows with shaded_m and walked_m filled in")
    passed = 0
    for r in rows:
        measured = 100 * float(r["shaded_m"]) / float(r["walked_m"])
        diff = abs(measured - float(r["model_pct"]))
        passed += diff <= 15
        print(f"segment {r['segment_id']:>5}  model {float(r['model_pct']):5.1f}%  measured {measured:5.1f}%  diff {diff:4.1f}  {'ok' if diff <= 15 else 'MISS'}")
    print(f"{passed}/{len(rows)} within 15 points")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        score(Path(sys.argv[1]))
    else:
        write()
