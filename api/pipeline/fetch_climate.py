"""Step 6. A month-by-hour temperature climatology for the pilot, used when there is no forecast.

Ten years of hourly ERA5 reanalysis temperatures from the Open-Meteo archive
API (keyless), averaged into a 12 x 24 table in local clock time. That is the
offline weather provider: "what is a typical 3 PM in July here".

    python -m pipeline.fetch_climate
"""

from __future__ import annotations

import json
from collections import defaultdict

import httpx

from .config import OUT, PILOT, RAW

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FIRST_YEAR, LAST_YEAR = 2015, 2024


def main() -> None:
    lat, lon = PILOT.centre
    cache = RAW / "open_meteo_archive.json"
    if cache.exists():
        payload = json.loads(cache.read_text())
    else:
        response = httpx.get(
            ARCHIVE_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": f"{FIRST_YEAR}-01-01",
                "end_date": f"{LAST_YEAR}-12-31",
                "hourly": "temperature_2m",
                "timezone": PILOT.timezone,
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        RAW.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload))

    sums: dict[tuple[int, int], float] = defaultdict(float)
    counts: dict[tuple[int, int], int] = defaultdict(int)
    for stamp, temp in zip(payload["hourly"]["time"], payload["hourly"]["temperature_2m"]):
        if temp is None:
            continue
        key = (int(stamp[5:7]), int(stamp[11:13]))
        sums[key] += float(temp)
        counts[key] += 1
    table = [[round(sums[(m, h)] / counts[(m, h)], 1) for h in range(24)] for m in range(1, 13)]
    out = {
        "source": f"Open-Meteo archive API (ERA5 reanalysis), hourly temperature_2m, {FIRST_YEAR} to {LAST_YEAR}",
        "location": {"lat": payload["latitude"], "lon": payload["longitude"]},
        "units": "degrees Celsius, mean by calendar month and local clock hour",
        "hours_averaged": sum(counts.values()),
        "mean_temp_c": table,
    }
    (OUT / "climatology.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"{out['hours_averaged']} hours; July 15:00 mean {table[6][15]} C, January 07:00 mean {table[0][7]} C")


if __name__ == "__main__":
    main()
