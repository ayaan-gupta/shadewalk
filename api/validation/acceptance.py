"""Measure the PRD's acceptance tests on the pilot and write docs/acceptance.json.

    python -m validation.acceptance

Every number in NOTES_FOR_README.md comes from this script or from the test
suite, which calls the same functions with smaller samples.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any

import numpy as np

from shadewalk.config import Settings
from shadewalk.network import Network
from shadewalk.routing import DEFAULT_WEIGHT, MAX_WEIGHT, heat_factor, plan
from shadewalk.shade.table import Layer, ShadeTable
from shadewalk.store import FileStore
from shadewalk.weather import ClimatologyWeather

from . import independent

DOCS = Path(__file__).resolve().parents[2] / "docs"
PAIR_SEED = 715
MIN_STRAIGHT_M, MAX_STRAIGHT_M = 300.0, 1500.0
JULY, THREE_PM = 7, 15 * 60


def sample_pairs(net: Network, count: int, seed: int = PAIR_SEED) -> list[tuple[int, int]]:
    """Seeded origin-destination node pairs a walk apart: 300 m to 1.5 km in a straight line."""
    rng = random.Random(seed)
    pairs: list[tuple[int, int]] = []
    while len(pairs) < count:
        a, b = rng.randrange(net.node_count), rng.randrange(net.node_count)
        d = float(np.hypot(net.node_x[a] - net.node_x[b], net.node_y[a] - net.node_y[b]))
        if MIN_STRAIGHT_M <= d <= MAX_STRAIGHT_M:
            pairs.append((a, b))
    return pairs


def shade_gain(net: Network, table: ShadeTable, pairs: list[tuple[int, int]], layer: Layer, weight: float, heat: float, month: int = JULY, minute: int = THREE_PM) -> dict[str, Any]:
    """Acceptance tests 1 and 2 for one shade layer and one slider value."""
    shade = table.segments(month, minute, layer)
    wins = identical = 0
    ratios: list[float] = []
    gains: list[float] = []
    for a, b in pairs:
        pair = plan(net, shade, a, b, weight, heat)
        assert pair is not None
        ratios.append(pair.detour_ratio)
        gains.append((pair.shadiest.shade_share - pair.shortest.shade_share) * 100)
        identical += pair.shortest.edges == pair.shadiest.edges
        # "At least 25% more shaded length". A shortest route with no shade at all is beaten by any shade.
        if pair.shadiest.shaded_m > pair.shortest.shaded_m and pair.shadiest.shaded_m >= 1.25 * pair.shortest.shaded_m:
            wins += 1
    return {
        "layer": layer,
        "weight": weight,
        "pairs": len(pairs),
        "pairs_with_25pct_more_shaded_length": wins,
        "share": round(wins / len(pairs), 3),
        "identical_routes": identical,
        "median_shade_gain_points": round(float(np.median(gains)), 1),
        "median_detour_ratio": round(float(np.median(ratios)), 3),
        "max_detour_ratio": round(max(ratios), 3),
    }


def latency(pairs: list[tuple[int, int]], net: Network) -> dict[str, Any]:
    """Acceptance test 4: full POST /api/route round trips through the ASGI app."""
    from fastapi.testclient import TestClient

    from shadewalk.main import create_app

    client = TestClient(create_app(Settings(DATABASE_URL="", WEATHER_PROVIDER="offline")))
    times: list[float] = []
    for a, b in pairs:
        body = {
            "origin": {"lon": float(net.node_lon[a]), "lat": float(net.node_lat[a])},
            "destination": {"lon": float(net.node_lon[b]), "lat": float(net.node_lat[b])},
            "depart_at": "2026-07-15T15:00",
        }
        started = time.perf_counter()
        response = client.post("/api/route", json=body)
        times.append((time.perf_counter() - started) * 1000)
        assert response.status_code == 200, response.text
    return {"requests": len(times), "p50_ms": round(float(np.percentile(times, 50)), 2), "p95_ms": round(float(np.percentile(times, 95)), 2), "max_ms": round(max(times), 2)}


def main() -> None:
    settings = Settings(DATABASE_URL="", WEATHER_PROVIDER="offline")
    data = FileStore(settings.data_dir).load()
    net, table = data.network, data.shade
    climate = ClimatologyWeather.from_file(settings.data_dir / "climatology.json")
    heat = heat_factor(climate._table[JULY - 1][15])
    pairs = sample_pairs(net, 200)

    checks = {f"{m:02d}-{h:02d}": independent.run(m, h) for m, h in ((7, 15), (1, 9), (4, 17))}
    report = {
        "pilot": data.meta["name"],
        "pairs": {"count": len(pairs), "seed": PAIR_SEED, "straight_line_m": [MIN_STRAIGHT_M, MAX_STRAIGHT_M]},
        "july_3pm": {"heat_factor": round(heat, 3), "mean_temp_c": climate._table[JULY - 1][15]},
        "test_1_shade_gain_default_slider": {layer: shade_gain(net, table, pairs, layer, DEFAULT_WEIGHT, heat) for layer in ("all", "buildings")},
        "test_2_detour_cap": {
            "default_slider": {layer: shade_gain(net, table, pairs, layer, DEFAULT_WEIGHT, heat)["max_detour_ratio"] for layer in ("all", "buildings")},
            "cap_at_default": 1.5,
            "slider_raised_to_max": shade_gain(net, table, pairs, "all", MAX_WEIGHT, heat),
            "all_daylight_hours_all_months_max_ratio": max(
                shade_gain(net, table, pairs[:40], "all", DEFAULT_WEIGHT, 1.5, month, hour * 60)["max_detour_ratio"] for month in (1, 4, 7, 10) for hour in (8, 11, 14, 17)
            ),
        },
        "test_3_independent_check": checks,
        "test_4_latency": latency(pairs, net),
    }
    DOCS.mkdir(exist_ok=True)
    (DOCS / "acceptance.json").write_text(json.dumps(report, indent=1) + "\n")
    summary = {
        "test_1": {k: (v["share"], v["pairs_with_25pct_more_shaded_length"], v["identical_routes"], v["median_shade_gain_points"]) for k, v in report["test_1_shade_gain_default_slider"].items()},
        "test_2": {k: v if not isinstance(v, dict) or "max_detour_ratio" not in v else v["max_detour_ratio"] for k, v in report["test_2_detour_cap"].items()},
        "test_3": {k: (v["max_diff_points"], v["mean_diff_points"], v["within_15_points"]) for k, v in checks.items()},
        "test_4": report["test_4_latency"],
    }
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
