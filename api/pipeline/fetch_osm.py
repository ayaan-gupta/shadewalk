"""Step 1. Pull the raw OpenStreetMap data for the pilot through osmnx and Overpass.

Everything lands in data/raw (git-ignored). osmnx caches each Overpass
response there too, so a second run makes no network calls.

    python -m pipeline.fetch_osm
"""

from __future__ import annotations

import json
import os
import socket
import time
import warnings
from datetime import UTC, datetime
from typing import Any, Callable, TypeVar
from urllib.parse import urlparse

import geopandas as gpd
import osmnx as ox
import pandas as pd
import requests

from .config import PILOT, RAW

T = TypeVar("T")

WAY_TAGS = [
    "highway", "footway", "name", "tunnel", "covered", "indoor", "level", "layer",
    "bridge", "access", "foot", "service", "crossing", "sidewalk",
]  # fmt: skip

POI_TAGS: dict[str, Any] = {
    "highway": ["bus_stop"],
    "railway": ["station", "tram_stop"],
    "amenity": [
        "school", "kindergarten", "college", "university",
        "drinking_water", "library", "community_centre",
    ],
    "leisure": ["park"],
    "tourism": ["museum", "attraction"],
}  # fmt: skip

TREE_TAGS: dict[str, Any] = {"natural": ["tree", "wood", "tree_row"], "landuse": ["forest"]}

ROAD_TAGS: dict[str, Any] = {
    "highway": [
        "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
        "residential", "living_street", "pedestrian",
    ]
}  # fmt: skip


def buffered_bbox(buffer_m: float) -> tuple[float, float, float, float]:
    w, s, e, n = PILOT.bbox
    dlat = buffer_m / 110_900
    dlon = buffer_m / 93_500
    return (w - dlon, s - dlat, e + dlon, n + dlat)


def with_retry(what: str, fn: Callable[[], T], attempts: int = 30) -> T:
    """Overpass refuses connections when it is busy. Wait and ask again."""
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # osmnx raises several unrelated types here
            if i == attempts - 1:
                raise
            print(f"  {what}: {type(exc).__name__}, retrying", flush=True)
            time.sleep(10)
    raise AssertionError("unreachable")


def impatient_sleep(seconds: float) -> None:
    """osmnx sleeps 55 s after every 504. On a day when Overpass rejects half of all
    requests that turns five queries into an hour, so cap each pause instead."""
    _real_sleep(min(seconds, 8.0))


_real_sleep = time.sleep

OVERPASS_CANDIDATES = [
    "https://overpass-api.de/api",
    "https://gall.openstreetmap.de/api",
    "https://lambert.openstreetmap.de/api",
]


def pick_overpass() -> str:
    """Choose an Overpass endpoint whose pinned address accepts connections.

    overpass-api.de is a round robin over two machines. osmnx resolves the name
    once with gethostbyname and pins every later request to that one address,
    so when the first record is the machine that is down, every request is
    refused even though the service as a whole is up. Probe the same way osmnx
    resolves, and fall through to the machines' own hostnames.
    """
    override = os.environ.get("OVERPASS_URL")
    for url in [override] if override else OVERPASS_CANDIDATES:
        host = urlparse(url).hostname or ""
        try:
            with socket.create_connection((socket.gethostbyname(host), 443), timeout=6):
                return url
        except OSError as exc:
            print(f"  {host}: {exc}")
    raise RuntimeError("no Overpass endpoint is reachable")


OSM_API = "https://api.openstreetmap.org/api/0.6/map"


def features_via_osm_api(bbox: tuple[float, float, float, float], tags: dict[str, Any]) -> gpd.GeoDataFrame:
    """Second source for the same data: the OSM API's map call, in four tiles to stay under its node limit.

    Used only when Overpass will not answer. It returns raw OSM XML for a bounding
    box, which osmnx can filter by tag exactly as it filters an Overpass response.
    """
    w, s, e, n = bbox
    mx, my = (w + e) / 2, (s + n) / 2
    folder = RAW / "osm-api"
    folder.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, tile in enumerate([(w, s, mx, my), (mx, s, e, my), (w, my, mx, n), (mx, my, e, n)]):
        path = folder / ("%.5f_%.5f_%.5f_%.5f.osm" % tile)
        if not path.exists():
            response = requests.get(OSM_API, params={"bbox": ",".join(f"{v:.5f}" for v in tile)}, headers={"User-Agent": "shadewalk-pilot-build/0.1"}, timeout=120)
            response.raise_for_status()
            path.write_bytes(response.content)
        try:
            frames.append(ox.features_from_xml(path, tags=tags))
        except ox._errors.InsufficientResponseError:
            continue
    merged = pd.concat(frames)
    return gpd.GeoDataFrame(merged[~merged.index.duplicated()], crs=frames[0].crs)


def features(what: str, bbox: tuple[float, float, float, float], tags: dict[str, Any], overpass_up: bool) -> gpd.GeoDataFrame:
    if overpass_up:
        try:
            return with_retry(what, lambda: ox.features_from_bbox(bbox, tags), attempts=6)
        except Exception as exc:
            print(f"  {what}: Overpass gave up ({type(exc).__name__}), using the OSM API map call", flush=True)
    return features_via_osm_api(bbox, tags)


def save(gdf: gpd.GeoDataFrame, name: str) -> None:
    keep = [c for c in gdf.columns if gdf[c].notna().any()]
    out = gdf[keep].reset_index()
    for col in out.columns:
        if col != "geometry" and out[col].dtype == object:
            out[col] = out[col].map(lambda v: v if v is None or isinstance(v, str) else json.dumps(v) if isinstance(v, (list, dict)) else str(v))
    path = RAW / f"{name}.geojson"
    out.to_file(path, driver="GeoJSON")
    print(f"  wrote {path.name}: {len(out)} features", flush=True)


def main() -> None:
    warnings.filterwarnings("ignore", category=FutureWarning)
    RAW.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(RAW / "osmnx-cache")
    ox.settings.requests_timeout = 90
    ox.settings.overpass_rate_limit = False
    ox._overpass.time.sleep = impatient_sleep  # type: ignore[attr-defined]
    ox.settings.useful_tags_way = sorted(set(ox.settings.useful_tags_way) | set(WAY_TAGS))

    wide = buffered_bbox(PILOT.buffer_m)
    print(f"pilot bbox {PILOT.bbox}, shadow-caster bbox {tuple(round(v, 5) for v in wide)}")
    try:
        ox.settings.overpass_url = pick_overpass()
        overpass_up = True
        print(f"overpass endpoint {ox.settings.overpass_url}")
    except RuntimeError as exc:
        overpass_up = False
        print(f"{exc}; anything not already cached comes from the OSM API map call")

    print("walk network")
    if overpass_up or not (RAW / "walk.graphml").exists():
        graph = with_retry(
            "graph",
            lambda: ox.graph_from_bbox(PILOT.bbox, network_type="walk", simplify=True, retain_all=True, truncate_by_edge=True),
        )
        ox.save_graphml(graph, RAW / "walk.graphml")
        print(f"  wrote walk.graphml: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} directed edges")
    else:
        print("  kept the walk.graphml already on disk")

    print("buildings")
    buildings = features("buildings", wide, {"building": True, "building:part": True}, overpass_up)
    buildings = buildings[buildings.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    save(buildings, "buildings")

    print("points of interest")
    save(features("pois", PILOT.bbox, POI_TAGS, overpass_up), "pois")

    print("mapped trees (fallback canopy and a cross-check)")
    save(features("trees", wide, TREE_TAGS, overpass_up), "trees")

    print("named roads (labels for unnamed sidewalks)")
    roads = features("roads", PILOT.bbox, ROAD_TAGS, overpass_up)
    save(roads[roads.geometry.geom_type.isin(["LineString", "MultiLineString"])], "roads")

    (RAW / "osm_pull.json").write_text(
        json.dumps({"pulled_at": datetime.now(UTC).isoformat(timespec="seconds"), "source": ox.settings.overpass_url if overpass_up else OSM_API}, indent=2)
    )


if __name__ == "__main__":
    main()
