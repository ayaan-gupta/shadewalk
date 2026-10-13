"""An independent computational check of the shade table. Not a field measurement.

Nobody has stood on these streets with a tape measure, so this is the next
best thing: a second implementation of the same physical model that shares no
code with the production one, compared on 20 sampled segments.

What is different from production (shadewalk.shade):

    production                              this check
    --------------------------------------  ---------------------------------------
    sun position from pvlib (stored table)  NOAA solar equations, written out below
    buildings rasterised to 1 m cells       building footprints as exact polygons
    one rotated suffix-maximum sweep        one ray per sample point toward the sun
    samples every 1 m                       samples every 0.25 m
    tangent plane from radii of curvature   series formula for metres per degree

What is shared: the input data (OSM footprints and heights, the canopy height
raster) and the model's assumptions (prisms, solid crowns, flat ground). A
wrong building height fools both. Only a person on site can catch that, which
is what docs/field-validation.md is for.

This module must not import anything from shadewalk.shade. A test enforces it.
"""

from __future__ import annotations

import gzip
import json
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from numpy.typing import NDArray

DATA = Path(__file__).resolve().parents[2] / "data" / "pilot"
SAMPLE_STEP_M = 0.25
RAY_STEP_M = 0.25
MAX_CANOPY_M = 30.0
SEGMENTS = 20
MIN_LENGTH_M = 30.0
SEED = 20260715

Array = NDArray[np.float64]


def noaa_sun(when_utc: datetime, lat: float, lon: float) -> tuple[float, float]:
    """Solar azimuth (clockwise from north) and elevation with refraction, in degrees.

    The NOAA Solar Calculator equations (Meeus, Astronomical Algorithms).
    """
    stamp = when_utc.astimezone(UTC)
    day = stamp.toordinal() + 1721424.5 + (stamp.hour + stamp.minute / 60 + stamp.second / 3600) / 24
    t = (day - 2451545.0) / 36525.0
    mean_long = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360
    mean_anom = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    ecc = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    m = math.radians(mean_anom)
    centre = math.sin(m) * (1.914602 - t * (0.004817 + 0.000014 * t)) + math.sin(2 * m) * (0.019993 - 0.000101 * t) + math.sin(3 * m) * 0.000289
    true_long = mean_long + centre
    omega = math.radians(125.04 - 1934.136 * t)
    app_long = true_long - 0.00569 - 0.00478 * math.sin(omega)
    obliq0 = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
    obliq = math.radians(obliq0 + 0.00256 * math.cos(omega))
    decl = math.asin(math.sin(obliq) * math.sin(math.radians(app_long)))
    y = math.tan(obliq / 2) ** 2
    l0 = math.radians(mean_long)
    eq_time = 4 * math.degrees(
        y * math.sin(2 * l0) - 2 * ecc * math.sin(m) + 4 * ecc * y * math.sin(m) * math.cos(2 * l0) - 0.5 * y * y * math.sin(4 * l0) - 1.25 * ecc * ecc * math.sin(2 * m)
    )
    minutes = stamp.hour * 60 + stamp.minute + stamp.second / 60
    true_solar = (minutes + eq_time + 4 * lon) % 1440
    hour_angle = math.radians(true_solar / 4 - 180 if true_solar >= 0 else true_solar / 4 + 180)
    phi = math.radians(lat)
    cos_zenith = math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(hour_angle)
    zenith = math.acos(min(max(cos_zenith, -1), 1))
    elevation = 90 - math.degrees(zenith)
    if elevation > 85:
        refraction = 0.0
    elif elevation > 5:
        te = math.tan(math.radians(elevation))
        refraction = (58.1 / te - 0.07 / te**3 + 0.000086 / te**5) / 3600
    elif elevation > -0.575:
        refraction = (1735 + elevation * (-518.2 + elevation * (103.4 + elevation * (-12.79 + elevation * 0.711)))) / 3600
    else:
        refraction = (-20.772 / math.tan(math.radians(elevation))) / 3600
    cos_az = (math.sin(phi) * math.cos(zenith) - math.sin(decl)) / (math.cos(phi) * math.sin(zenith))
    az = math.degrees(math.acos(min(max(cos_az, -1), 1)))
    azimuth = (az + 180) % 360 if hour_angle > 0 else (540 - az) % 360
    return azimuth, elevation + refraction


def metres_per_degree(lat: float) -> tuple[float, float]:
    """(per degree of longitude, per degree of latitude), by the usual cosine series."""
    p = math.radians(lat)
    return (
        111412.84 * math.cos(p) - 93.5 * math.cos(3 * p) + 0.118 * math.cos(5 * p),
        111132.92 - 559.82 * math.cos(2 * p) + 1.175 * math.cos(4 * p) - 0.0023 * math.cos(6 * p),
    )


@dataclass
class World:
    """The inputs, converted to metres east and north of the dataset origin."""

    meta: dict[str, Any]
    edges: list[dict[str, Any]]
    # (rings as [n, 2] arrays, height, xmin, ymin, xmax, ymax)
    prisms: list[tuple[list[Array], float, float, float, float, float]]
    canopy: Array

    @staticmethod
    def load(data_dir: Path = DATA) -> World:
        meta = json.loads((data_dir / "meta.json").read_text())
        mx, my = metres_per_degree(meta["frame"]["lat0"])
        lon0, lat0 = meta["frame"]["lon0"], meta["frame"]["lat0"]

        def xy(coords: list[list[float]]) -> Array:
            a = np.asarray(coords, dtype=np.float64)
            return np.column_stack([(a[:, 0] - lon0) * mx, (a[:, 1] - lat0) * my])

        with gzip.open(data_dir / "network.json.gz") as fh:
            edges = json.loads(fh.read())["edges"]
        for e in edges:
            e["xy"] = xy(e["coords"])
        with gzip.open(data_dir / "buildings.geojson.gz") as fh:
            features = json.loads(fh.read())["features"]
        prisms = []
        for f in features:
            rings = [xy(r) for r in f["geometry"]["coordinates"]]
            prisms.append((rings, float(f["properties"]["h"]), *rings[0].min(axis=0), *rings[0].max(axis=0)))
        with np.load(data_dir / "rasters.npz") as z:
            canopy = z["canopy_dm"].astype(np.float64) / 10
        return World(meta=meta, edges=edges, prisms=prisms, canopy=canopy)

    def canopy_at(self, x: Array, y: Array) -> Array:
        g = self.meta["grid"]
        col = np.floor((x - g["x_min"]) / g["res"]).astype(int)
        row = np.floor((g["y_max"] - y) / g["res"]).astype(int)
        ok = (row >= 0) & (row < g["height"]) & (col >= 0) & (col < g["width"])
        out = np.zeros(x.shape)
        out[ok] = self.canopy[row[ok], col[ok]]
        return out


def points_along(xy: Array, step: float) -> Array:
    seg = np.hypot(*np.diff(xy, axis=0).T)
    total = seg.sum()
    n = max(1, int(round(total / step)))
    at = (np.arange(n) + 0.5) * total / n
    cum = np.concatenate([[0], np.cumsum(seg)])
    return np.column_stack([np.interp(at, cum, xy[:, 0]), np.interp(at, cum, xy[:, 1])])


def inside_ring(pts: Array, ring: Array) -> NDArray[np.bool_]:
    """Even-odd rule, every point against every edge of one ring."""
    x, y = pts[:, 0][:, None], pts[:, 1][:, None]
    x1, y1, x2, y2 = ring[:-1, 0], ring[:-1, 1], ring[1:, 0], ring[1:, 1]
    straddles = (y1 > y) != (y2 > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        cross_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
    hits: NDArray[np.bool_] = (np.sum(straddles & (x < cross_x), axis=1) % 2) == 1
    return hits


def ray_crosses_ring(pts: Array, ends: Array, ring: Array) -> NDArray[np.bool_]:
    """Does the segment from each point to its end cross any edge of the ring."""
    px, py = pts[:, 0][:, None], pts[:, 1][:, None]
    rx, ry = (ends[:, 0] - pts[:, 0])[:, None], (ends[:, 1] - pts[:, 1])[:, None]
    ax, ay = ring[:-1, 0], ring[:-1, 1]
    sx, sy = ring[1:, 0] - ax, ring[1:, 1] - ay
    denom = rx * sy - ry * sx
    with np.errstate(divide="ignore", invalid="ignore"):
        t = ((ax - px) * sy - (ay - py) * sx) / denom
        u = ((ax - px) * ry - (ay - py) * rx) / denom
    hit = (denom != 0) & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)
    out: NDArray[np.bool_] = hit.any(axis=1)
    return out


def segment_shade(world: World, edge: dict[str, Any], azimuth: float, elevation: float, canopy: bool = True) -> float:
    """Fraction of a segment's length that is shaded or under cover, by brute force."""
    if edge["covered"] or elevation <= 0:
        return 1.0
    pts = points_along(edge["xy"], SAMPLE_STEP_M)
    tan_el = math.tan(math.radians(elevation))
    toward = np.array([math.sin(math.radians(azimuth)), math.cos(math.radians(azimuth))])
    shaded = np.zeros(len(pts), dtype=bool)

    for rings, height, xmin, ymin, xmax, ymax in world.prisms:
        reach = height / tan_el
        ends = pts + toward * reach
        lo = np.minimum(pts, ends).min(axis=0)
        hi = np.maximum(pts, ends).max(axis=0)
        if hi[0] < xmin or lo[0] > xmax or hi[1] < ymin or lo[1] > ymax:
            continue
        within = inside_ring(pts, rings[0])
        crosses = ray_crosses_ring(pts, ends, rings[0])
        for hole in rings[1:]:
            within &= ~inside_ring(pts, hole)
            crosses |= ray_crosses_ring(pts, ends, hole)
        shaded |= within | crosses

    if canopy:
        shaded |= world.canopy_at(pts[:, 0], pts[:, 1]) > 0
        for d in np.arange(RAY_STEP_M, MAX_CANOPY_M / tan_el + RAY_STEP_M, RAY_STEP_M):
            if shaded.all():
                break
            probe = pts + toward * d
            shaded |= world.canopy_at(probe[:, 0], probe[:, 1]) > d * tan_el
    return float(shaded.mean())


def pick_segments(world: World, production: NDArray[np.floating], count: int = SEGMENTS, seed: int = SEED) -> list[int]:
    """A seeded sample, a third each from the sunny, mixed and shady ends of the table."""
    rng = random.Random(seed)
    eligible = [e["id"] for e in world.edges if e["length_m"] >= MIN_LENGTH_M and not e["covered"]]
    bands = [[i for i in eligible if production[i] < 0.2], [i for i in eligible if 0.2 <= production[i] < 0.6], [i for i in eligible if production[i] >= 0.6]]
    quota = [count // 3 + (1 if b < count % 3 else 0) for b in range(3)]
    picked: list[int] = []
    for band, n in zip(bands, quota):
        picked += rng.sample(band, min(n, len(band)))
    return sorted(picked)


def local_noon_slot(world: World, month: int, hour: int) -> tuple[float, float]:
    """This check's own sun position for the table's representative day."""
    day, year = 15, 2025
    when = datetime(year, month, day, hour, tzinfo=ZoneInfo(world.meta["timezone"]))
    w, s, e, n = world.meta["bbox"]
    return noaa_sun(when.astimezone(UTC), (s + n) / 2, (w + e) / 2)


def run(month: int = 7, hour: int = 15, data_dir: Path = DATA) -> dict[str, Any]:
    world = World.load(data_dir)
    with np.load(data_dir / "shade.npz") as z:
        production = z["segments_all"][month - 1, hour].astype(np.float64) / 250
    july = production
    if (month, hour) != (7, 15):
        with np.load(data_dir / "shade.npz") as z:
            july = z["segments_all"][6, 15].astype(np.float64) / 250
    ids = pick_segments(world, july)
    azimuth, elevation = local_noon_slot(world, month, hour)
    rows = []
    for i in ids:
        edge = world.edges[i]
        check = segment_shade(world, edge, azimuth, elevation)
        mid = edge["coords"][len(edge["coords"]) // 2]
        rows.append({
            "segment_id": i,
            "street": edge.get("street"),
            "kind": edge["kind"],
            "length_m": edge["length_m"],
            "start": edge["coords"][0],
            "end": edge["coords"][-1],
            "mid": mid,
            "model_pct": round(float(production[i]) * 100, 1),
            "check_pct": round(check * 100, 1),
            "diff_points": round(abs(float(production[i]) - check) * 100, 1),
        })  # fmt: skip
    diffs = [r["diff_points"] for r in rows]
    return {
        "what": "independent computational check (ray casting against vector footprints), not a field measurement",
        "month": month,
        "hour": hour,
        "sun_noaa": {"azimuth": round(azimuth, 2), "elevation": round(elevation, 2)},
        "segments": rows,
        "max_diff_points": max(diffs),
        "mean_diff_points": round(sum(diffs) / len(diffs), 2),
        "within_15_points": sum(d <= 15 for d in diffs),
        "count": len(diffs),
    }


if __name__ == "__main__":
    for month, hour in ((7, 15), (1, 9), (4, 17)):
        result = run(month, hour)
        print(f"month {month} hour {hour}: sun {result['sun_noaa']}, max diff {result['max_diff_points']} points, mean {result['mean_diff_points']}, {result['within_15_points']}/{result['count']} within 15")
        if (month, hour) == (7, 15):
            for r in result["segments"]:
                print(f"  seg {r['segment_id']:5d} {r['length_m']:6.1f} m  model {r['model_pct']:5.1f}%  check {r['check_pct']:5.1f}%  diff {r['diff_points']:4.1f}  {r['street'] or ''}")
