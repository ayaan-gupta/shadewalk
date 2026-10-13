"""Step 5. Precompute the shade table: every segment, every hour, one day per month.

For each of the 12 x 24 slots the sun position comes from pvlib, shadows are
cast twice (buildings only, then buildings plus canopy) and each segment gets
the fraction of its one-metre samples that are shaded. Routing then never does
geometry, only lookups.

    python -m pipeline.build_shade
"""

from __future__ import annotations

import json
import time
from typing import Any

import numpy as np
from numpy.typing import NDArray

from shadewalk.geo import Grid, sample_polyline
from shadewalk.shade.raster import cast_shadow, shade_fraction
from shadewalk.shade.table import SCALE

from .config import MIN_SUN_ELEVATION_DEG, OUT, PILOT, RAW, REFERENCE_YEAR, REPRESENTATIVE_DAY, SAMPLE_SPACING_M, SUN_SLOT_MINUTES
from .grid import pilot_frame, pilot_grid
from .io import read_json_gz
from .sun import sun_table

# A bus stop is "shaded" by the share of ground within this radius that is.
STOP_RADIUS_M = 3.0


def segment_samples(edges: list[dict[str, Any]]) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.int64]]:
    frame = pilot_frame()
    xs: list[NDArray[np.float64]] = []
    ys: list[NDArray[np.float64]] = []
    counts: list[int] = []
    for edge in edges:
        coords = np.array(edge["coords"])
        x, y = frame.to_xy(coords[:, 0], coords[:, 1])
        sx, sy = sample_polyline(x, y, SAMPLE_SPACING_M)
        xs.append(sx)
        ys.append(sy)
        counts.append(len(sx))
    return np.concatenate(xs), np.concatenate(ys), np.array(counts, dtype=np.int64)


def poi_samples(pois: list[dict[str, Any]]) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.int64]]:
    """A small disc of points around each point of interest."""
    frame = pilot_frame()
    r = int(STOP_RADIUS_M)
    dx, dy = np.meshgrid(np.arange(-r, r + 1), np.arange(-r, r + 1))
    disc = dx**2 + dy**2 <= STOP_RADIUS_M**2
    ox, oy = dx[disc].astype(np.float64), dy[disc].astype(np.float64)
    px, py = frame.to_xy([p["lon"] for p in pois], [p["lat"] for p in pois])
    xs = (px[:, None] + ox[None, :]).ravel()
    ys = (py[:, None] + oy[None, :]).ravel()
    return xs, ys, np.full(len(pois), len(ox), dtype=np.int64)


def lookup(raster: NDArray[np.bool_], grid: Grid, x: NDArray[np.float64], y: NDArray[np.float64]) -> NDArray[np.bool_]:
    row, col = grid.rowcol(x, y)
    ok = grid.inside(row, col)
    out = np.zeros(len(x), dtype=bool)
    out[ok] = raster[row[ok], col[ok]]
    return out


def main() -> None:
    grid = pilot_grid()
    rasters = np.load(OUT / "rasters.npz")
    building = rasters["building_dm"].astype(np.float32) / 10
    canopy = rasters["canopy_dm"].astype(np.float32) / 10
    surfaces = {"buildings": building, "all": np.maximum(building, canopy)}

    network = read_json_gz(OUT / "network.json.gz")
    edges: list[dict[str, Any]] = network["edges"]
    pois: list[dict[str, Any]] = json.loads((OUT / "pois.json").read_text())
    sx, sy, s_counts = segment_samples(edges)
    px, py, p_counts = poi_samples(pois)
    always_covered = np.array([e["covered"] for e in edges], dtype=bool)

    under = {name: (lookup(h > 0, grid, sx, sy), lookup(h > 0, grid, px, py)) for name, h in surfaces.items()}
    azimuth, elevation = sun_table()
    per_hour = 60 // SUN_SLOT_MINUTES

    seg_table = {name: np.full((12, 24, len(edges)), SCALE, dtype=np.uint8) for name in surfaces}
    poi_table = {name: np.full((12, 24, len(pois)), SCALE, dtype=np.uint8) for name in surfaces}
    daylight_slots = 0
    started = time.time()
    for month in range(12):
        for hour in range(24):
            az = float(azimuth[month, hour * per_hour])
            el = float(elevation[month, hour * per_hour])
            if el < MIN_SUN_ELEVATION_DEG:
                continue
            daylight_slots += 1
            for name, height in surfaces.items():
                shadow = cast_shadow(height, grid, az, el)
                seg = shade_fraction(shadow.at(sx, sy) | under[name][0], s_counts)
                seg[always_covered] = 1.0
                seg_table[name][month, hour] = np.round(seg * SCALE).astype(np.uint8)
                poi = shade_fraction(shadow.at(px, py) | under[name][1], p_counts)
                poi_table[name][month, hour] = np.round(poi * SCALE).astype(np.uint8)
        print(f"  month {month + 1:2d} done, {time.time() - started:5.1f}s", flush=True)

    np.savez_compressed(
        OUT / "shade.npz",
        segments_all=seg_table["all"],
        segments_buildings=seg_table["buildings"],
        pois_all=poi_table["all"],
        pois_buildings=poi_table["buildings"],
        sun_azimuth=np.round(azimuth, 2),
        sun_elevation=np.round(elevation, 2),
    )

    lengths = np.array([e["length_m"] for e in edges])
    july_3pm = {name: float((seg_table[name][6, 15] / SCALE * lengths).sum() / lengths.sum()) for name in surfaces}
    stats = {
        "segments": len(edges),
        "samples": int(len(sx)),
        "sample_spacing_m": SAMPLE_SPACING_M,
        "daylight_slots": daylight_slots,
        "representative_day": f"day {REPRESENTATIVE_DAY} of each month, {REFERENCE_YEAR}, {PILOT.timezone} clock time",
        "min_sun_elevation_deg": MIN_SUN_ELEVATION_DEG,
        "samples_inside_building_footprints_share": round(float(under["buildings"][0].mean()), 4),
        "samples_under_canopy_share": round(float((under["all"][0] & ~under["buildings"][0]).mean()), 4),
        "always_covered_segments": int(always_covered.sum()),
        "july_3pm_sun": {"azimuth": round(float(azimuth[6, 15 * per_hour]), 1), "elevation": round(float(elevation[6, 15 * per_hour]), 1)},
        "july_3pm_network_shade_share": {k: round(v, 3) for k, v in july_3pm.items()},
        "seconds": round(time.time() - started, 1),
    }
    (RAW / "shade_stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
