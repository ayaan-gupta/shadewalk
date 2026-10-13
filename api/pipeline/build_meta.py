"""Step 7. Write meta.json: what the dataset is, where it came from and what the model assumed.

    python -m pipeline.build_meta
"""

from __future__ import annotations

import json
from typing import Any

from .config import (
    DEFAULT_BUILDING_HEIGHT_M,
    DEFAULT_CANOPY_HEIGHT_M,
    METRES_PER_LEVEL,
    MIN_SUN_ELEVATION_DEG,
    OUT,
    PILOT,
    RAW,
    REFERENCE_YEAR,
    REPRESENTATIVE_DAY,
    SAMPLE_SPACING_M,
)
from .grid import pilot_frame, pilot_grid


def read(name: str) -> dict[str, Any]:
    path = RAW / name
    return json.loads(path.read_text()) if path.exists() else {}


def main() -> None:
    frame, grid = pilot_frame(), pilot_grid()
    surface, shade, network = read("surface_stats.json"), read("shade_stats.json"), read("network_stats.json")
    imagery = surface.get("imagery", {})
    naip_tiles = (imagery.get("naip") or {}).get("tiles", [])
    lidar = imagery.get("lidar") or {}
    meta = {
        "slug": PILOT.slug,
        "name": PILOT.name,
        "bbox": list(PILOT.bbox),
        "timezone": PILOT.timezone,
        "frame": {"lat0": frame.lat0, "lon0": frame.lon0},
        "grid": grid.to_dict(),
        "sources": {
            "osm": {"pulled_at": read("osm_pull.json").get("pulled_at"), "via": "osmnx: Overpass for the walk graph, " + ("Overpass" if "overpass" in str(read("osm_pull.json").get("source", "")) else "the OSM API map call") + " for buildings, places, trees and road names", "licence": "ODbL, (c) OpenStreetMap contributors"},
            "naip": [{"item": t["item"], "acquired": t["datetime"], "gsd_m": t["gsd_m"]} for t in naip_tiles],
            "lidar": {k: {"item": v["item"], "native_res_m": v["native_res_m"]} for k, v in lidar.items()} if lidar else None,
            "imagery_via": "Microsoft Planetary Computer STAC",
            "climatology": json.loads((OUT / "climatology.json").read_text())["source"],
        },
        "model": {
            "building_height_rule": f"OSM height, else {METRES_PER_LEVEL:g} m per building:levels, else {DEFAULT_BUILDING_HEIGHT_M:g} m",
            "canopy_height_rule": f"lidar first return minus ground where it reads a crown, else {DEFAULT_CANOPY_HEIGHT_M:g} m",
            "representative_day": f"day {REPRESENTATIVE_DAY} of each month, {REFERENCE_YEAR}",
            "sample_spacing_m": SAMPLE_SPACING_M,
            "min_sun_elevation_deg": MIN_SUN_ELEVATION_DEG,
            "shadow_buffer_m": PILOT.buffer_m,
        },
        "stats": {"network": network.get("network"), "pois": network.get("pois"), "buildings": surface.get("buildings"), "canopy": surface.get("canopy"), "shade": shade},
    }
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(f"wrote meta.json for {PILOT.name}")


if __name__ == "__main__":
    main()
