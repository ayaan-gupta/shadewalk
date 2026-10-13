# Field validation protocol

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
| 189 | San Jacinto Street | path | 36 | 32.78160, -96.80408 | 32.78142, -96.80438 | 28% | 26% |
| 343 | unnamed path | service | 54 | 32.78794, -96.79502 | 32.78829, -96.79543 | 0% | 1% |
| 502 | South Griffin Street | path | 49 | 32.77961, -96.80226 | 32.77975, -96.80275 | 0% | 0% |
| 635 | Browder Street | path | 60 | 32.77769, -96.79641 | 32.77724, -96.79675 | 42% | 39% |
| 732 | Wood Street | sidewalk | 71 | 32.77787, -96.80154 | 32.77764, -96.80224 | 0% | 0% |
| 792 | South Austin Street | sidewalk | 66 | 32.77797, -96.80487 | 32.77855, -96.80505 | 0% | 0% |
| 900 | South Saint Paul Street | service | 46 | 32.77880, -96.79517 | 32.77920, -96.79530 | 4% | 4% |
| 961 | Pacific Avenue | sidewalk | 31 | 32.78319, -96.79428 | 32.78327, -96.79396 | 0% | 0% |
| 966 | North Saint Paul Street | sidewalk | 65 | 32.78282, -96.79604 | 32.78225, -96.79587 | 77% | 77% |
| 1056 | Elm Street | sidewalk | 38 | 32.78258, -96.79430 | 32.78266, -96.79391 | 26% | 26% |
| 1246 | Flora Street | sidewalk | 60 | 32.78952, -96.79830 | 32.78913, -96.79876 | 28% | 29% |
| 1268 | Woodall Rodgers Freeway | path | 100 | 32.79025, -96.80030 | 32.78962, -96.80106 | 46% | 48% |
| 1737 | San Jacinto Street | sidewalk | 48 | 32.78612, -96.79843 | 32.78589, -96.79886 | 45% | 47% |
| 1848 | Federal Street | sidewalk | 57 | 32.78294, -96.80015 | 32.78323, -96.79970 | 72% | 71% |
| 2267 | South Akard Street | sidewalk | 47 | 32.77994, -96.79929 | 32.78035, -96.79941 | 88% | 86% |
| 2522 | Alamo Street | service | 48 | 32.78747, -96.80559 | 32.78726, -96.80514 | 37% | 37% |
| 2695 | unnamed path | service | 43 | 32.78910, -96.79447 | 32.78882, -96.79415 | 0% | 0% |
| 3030 | North Saint Paul Street | sidewalk | 32 | 32.78175, -96.79589 | 32.78147, -96.79581 | 100% | 100% |
| 3037 | Main Street | sidewalk | 70 | 32.78135, -96.79634 | 32.78120, -96.79706 | 94% | 94% |
| 3152 | Leonard Street | sidewalk | 41 | 32.78774, -96.79441 | 32.78800, -96.79472 | 100% | 100% |

Sampling: seeded (`20260715`), segments of at least 30 m, seven from the sunny end of the table (under 20%), seven from the middle and six from the shady end (60% and over), so that agreement is tested across the range and not only where everything is in full sun.
