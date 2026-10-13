"""Step 4. Build the two things that cast shadows: building prisms and tree canopy.

Buildings come from OSM footprints with OSM heights. Canopy is segmented from
the NAIP aerial image. Both are written as vectors (for the map, PostGIS and the
independent check) and as one height raster each (for the shadow caster).

    python -m pipeline.build_surface            # NAIP canopy, lidar heights if present
    python -m pipeline.build_surface --canopy osm   # fallback: mapped OSM trees only
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio.features
from affine import Affine
from numpy.typing import NDArray
from scipy import ndimage as ndi
from shapely import make_valid, transform
from shapely.geometry import MultiPolygon, Point, Polygon, mapping, shape
from shapely.ops import unary_union

from shadewalk.geo import Grid

from .config import (
    DEFAULT_BUILDING_HEIGHT_M,
    DEFAULT_CANOPY_HEIGHT_M,
    MAX_CANOPY_HEIGHT_M,
    METRES_PER_LEVEL,
    MIN_CANOPY_HEIGHT_M,
    OUT,
    PILOT,
    RAW,
)
from .grid import pilot_frame, pilot_grid
from .io import write_json_gz

# An open-sided roof (bus shelter canopy, petrol station) is not a nine metre block.
ROOF_ONLY_HEIGHT_M = 4.0
NDVI_THRESHOLD = 0.10
TREE_MIN_HEIGHT_M = 2.5
MIN_CANOPY_PATCH_M2 = 4
# The image and the lidar are registered to about a crown edge, not a pixel.
CROWN_EDGE_TOLERANCE_PX = 2
BUILDING_EDGE_MARGIN_PX = 2
OSM_TREE_CROWN_RADIUS_M = 3.5


@dataclass
class Prism:
    polygon: Polygon
    height: float
    source: str
    name: str | None
    osm: str
    part: bool


def parse_metres(raw: Any) -> float | None:
    """OSM heights are free text: '24.5', '30 m', '120 ft', "45'"."""
    if not isinstance(raw, str):
        return None
    match = re.match(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*(m|metres?|meters?|ft|feet|')?\s*$", raw.lower())
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    if match.group(2) in ("ft", "feet", "'"):
        value *= 0.3048
    return value if 1.0 <= value <= 700.0 else None


def parse_levels(raw: Any) -> float | None:
    if not isinstance(raw, str):
        return None
    try:
        value = float(raw.split(";")[0])
    except ValueError:
        return None
    return value if 0.5 <= value <= 200 else None


def tagged_height(row: Any) -> tuple[float, str] | None:
    height = parse_metres(row.get("height"))
    if height is not None:
        return height, "height"
    levels = parse_levels(row.get("building:levels"))
    if levels is not None:
        return levels * METRES_PER_LEVEL, "levels"
    return None


def to_local(geom: Any) -> Any:
    frame = pilot_frame()

    def convert(coords: NDArray[np.float64]) -> NDArray[np.float64]:
        x, y = frame.to_xy(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])

    return transform(geom, convert)


def to_lonlat(geom: Any, digits: int = 7) -> Any:
    frame = pilot_frame()

    def convert(coords: NDArray[np.float64]) -> NDArray[np.float64]:
        lon, lat = frame.to_lonlat(coords[:, 0], coords[:, 1])
        return np.round(np.column_stack([lon, lat]), digits)

    return transform(geom, convert)


def polygons_of(geom: Any) -> list[Polygon]:
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def load_prisms() -> tuple[list[Prism], dict[str, Any]]:
    """Flatten OSM buildings and building parts into prisms that stand on the ground.

    Where a building is modelled in parts, the parts carry the real heights and
    the outline only repeats the tallest one. So a part replaces the outline
    over its own area, and the outline height is kept only for whatever area no
    part covers. `min_height` is ignored: every prism is solid down to the ground.
    """
    raw = gpd.read_file(RAW / "buildings.geojson")
    raw["geometry"] = raw.geometry.map(lambda g: make_valid(to_local(g)))
    is_part = raw["building:part"].notna() if "building:part" in raw else np.zeros(len(raw), dtype=bool)
    outlines, parts = raw[~is_part & raw["building"].notna()], raw[is_part]

    part_geoms = list(parts.geometry)
    part_points = [g.representative_point() for g in part_geoms]
    prisms: list[Prism] = []
    counts = {"height": 0, "levels": 0, "default": 0, "roof": 0, "inherited": 0}
    area = dict.fromkeys(counts, 0.0)

    def add(poly: Polygon, height: float, source: str, row: Any, part: bool) -> None:
        if poly.area < 1.0:
            return
        name = row.get("name") if isinstance(row.get("name"), str) else None
        prisms.append(Prism(poly, round(height, 1), source, name, f"{row['element']}/{row['id']}", part))
        counts[source] += 1
        area[source] += poly.area

    owner_height: dict[int, tuple[float, str]] = {}
    for _, row in outlines.iterrows():
        geom = row.geometry
        tagged = tagged_height(row)
        if tagged is not None:
            height, source = tagged
        elif row.get("building") == "roof":
            height, source = ROOF_ONLY_HEIGHT_M, "roof"
        else:
            height, source = DEFAULT_BUILDING_HEIGHT_M, "default"
        inside = [i for i, pt in enumerate(part_points) if geom.contains(pt)]
        for i in inside:
            owner_height[i] = (height, source)
        remainder = geom.difference(unary_union([part_geoms[i] for i in inside]).buffer(0.05)) if inside else geom
        for poly in polygons_of(remainder):
            add(poly, height, source, row, part=False)

    for i, (_, row) in enumerate(parts.iterrows()):
        tagged = tagged_height(row)
        if tagged is not None:
            height, source = tagged
        elif i in owner_height:
            height, source = owner_height[i][0], "inherited"
        else:
            height, source = DEFAULT_BUILDING_HEIGHT_M, "default"
        for poly in polygons_of(row.geometry):
            add(poly, height, source, row, part=True)

    total = sum(area.values())
    stats = {
        "osm_outlines": int(len(outlines)),
        "osm_parts": int(len(parts)),
        "prisms": len(prisms),
        "prisms_by_height_source": counts,
        "footprint_share_by_height_source": {k: round(v / total, 3) for k, v in area.items()},
        "default_height_m": DEFAULT_BUILDING_HEIGHT_M,
        "metres_per_level": METRES_PER_LEVEL,
    }
    return prisms, stats


def affine_of(grid: Grid) -> Affine:
    return Affine(grid.res, 0, grid.x_min, 0, -grid.res, grid.y_max)


def rasterize_prisms(prisms: list[Prism], grid: Grid) -> NDArray[np.float32]:
    """Height of the tallest prism over each cell centre."""
    ordered = sorted(prisms, key=lambda p: p.height)
    out: NDArray[np.float32] = rasterio.features.rasterize(
        ((mapping(p.polygon), p.height) for p in ordered),
        out_shape=grid.shape,
        transform=affine_of(grid),
        fill=0.0,
        dtype="float32",
    )
    return out


def lidar_height_above_ground() -> NDArray[np.float32] | None:
    """First-return surface minus a ground surface interpolated from ground-classified returns."""
    path = RAW / "lidar.npz"
    if not path.exists():
        return None
    data = np.load(path)
    dsm = data["dsm"].astype(np.float32)
    valid = (dsm > -1000) & (dsm < 600)
    ground = (data["classification"] == 2) & valid
    if ground.mean() < 0.05:
        return None
    nearest = ndi.distance_transform_edt(~ground, return_distances=False, return_indices=True)
    surface = dsm[nearest[0], nearest[1]]
    surface = ndi.uniform_filter(ndi.minimum_filter(surface, size=9), size=15)
    return np.where(valid, np.maximum(dsm - surface, 0), 0).astype(np.float32)


def compare_with_lidar(prisms: list[Prism], building: NDArray[np.float32], hag: NDArray[np.float32], grid: Grid) -> dict[str, Any]:
    """How far OSM heights sit from the 2018 lidar surface. A report, not an input."""
    labels: NDArray[np.int32] = rasterio.features.rasterize(
        ((mapping(p.polygon), i + 1) for i, p in sorted(enumerate(prisms), key=lambda ip: ip[1].height)),
        out_shape=grid.shape,
        transform=affine_of(grid),
        fill=0,
        dtype="int32",
    )
    order = np.argsort(labels, axis=None)
    flat_labels = labels.ravel()[order]
    starts = np.searchsorted(flat_labels, np.arange(1, len(prisms) + 1))
    ends = np.searchsorted(flat_labels, np.arange(1, len(prisms) + 1), side="right")
    flat_hag = hag.ravel()[order]
    rows: dict[str, list[tuple[float, float]]] = {}
    for prism, a, b in zip(prisms, starts, ends):
        if b - a < 25:
            continue
        rows.setdefault(prism.source, []).append((prism.height, float(np.percentile(flat_hag[a:b], 90))))
    report: dict[str, Any] = {}
    for source, pairs in sorted(rows.items()):
        osm, lidar = np.array(pairs).T
        report[source] = {
            "prisms": len(pairs),
            "median_osm_m": round(float(np.median(osm)), 1),
            "median_lidar_m": round(float(np.median(lidar)), 1),
            "median_abs_diff_m": round(float(np.median(np.abs(osm - lidar))), 1),
        }
    return report


def segment_canopy_naip(building: NDArray[np.float32], hag: NDArray[np.float32] | None) -> tuple[NDArray[np.float32], dict[str, Any]]:
    """Tree canopy from NAIP: NDVI finds vegetation, a height cue separates trees from lawn.

    NDVI = (NIR - red) / (NIR + red) on the raw digital numbers. Anything above
    the threshold is vegetation of some kind. To tell crown from grass the cue
    is height: the 3DEP lidar first-return surface stands at least 2.5 m above
    ground within two cells of the pixel. Local texture was the other candidate
    and is measured here for the record, but in this image it does not separate
    the two classes.
    """
    naip = np.load(RAW / "naip.npz")
    red, nir = naip["red"].astype(np.float32), naip["nir"].astype(np.float32)
    ndvi = (nir - red) / (nir + red + 1e-6)
    vegetation = (ndvi > NDVI_THRESHOLD) & naip["covered"]
    near_building = ndi.binary_dilation(building > 0, iterations=BUILDING_EDGE_MARGIN_PX)
    stats: dict[str, Any] = {
        "method": "NAIP NDVI > %.2f, kept where 2018 3DEP lidar stands >= %.1f m above ground within %d cells, OSM building footprints removed"
        % (NDVI_THRESHOLD, TREE_MIN_HEIGHT_M, CROWN_EDGE_TOLERANCE_PX),
        "vegetation_share_of_grid": round(float(vegetation.mean()), 4),
    }

    if hag is None:
        # No height cue at all: fall back to texture, the weaker classical cue.
        mean = ndi.uniform_filter(nir, 5)
        texture = np.sqrt(np.maximum(ndi.uniform_filter(nir * nir, 5) - mean * mean, 0))
        canopy = vegetation & (texture > 12) & ~near_building
        height = np.where(canopy, DEFAULT_CANOPY_HEIGHT_M, 0).astype(np.float32)
        stats["method"] = "NAIP NDVI > %.2f and 5x5 NIR standard deviation > 12 (no lidar available), all crowns %.0f m" % (NDVI_THRESHOLD, DEFAULT_CANOPY_HEIGHT_M)
    else:
        free_hag = np.where(near_building, 0, hag)
        tall = free_hag >= TREE_MIN_HEIGHT_M
        canopy = vegetation & ndi.binary_dilation(tall, iterations=CROWN_EDGE_TOLERANCE_PX) & ~(building > 0)
        crown_top = ndi.maximum_filter(free_hag, size=2 * CROWN_EDGE_TOLERANCE_PX + 1)
        measured = (crown_top >= MIN_CANOPY_HEIGHT_M) & canopy
        height = np.where(measured, np.clip(crown_top, MIN_CANOPY_HEIGHT_M, MAX_CANOPY_HEIGHT_M), DEFAULT_CANOPY_HEIGHT_M)
        height = np.where(canopy, np.round(height * 2) / 2, 0).astype(np.float32)

        mean = ndi.uniform_filter(nir, 5)
        texture = np.sqrt(np.maximum(ndi.uniform_filter(nir * nir, 5) - mean * mean, 0))
        lawn = vegetation & (hag < 1.0) & ~near_building
        trees = vegetation & tall
        stats["texture_cue_tested"] = {
            "what": "5x5 standard deviation of NIR, median over lidar-tall vs lidar-low vegetation",
            "tall_vegetation": round(float(np.median(texture[trees])), 1),
            "low_vegetation": round(float(np.median(texture[lawn])), 1),
        }
        stats["vegetation_that_is_tall_share"] = round(float(trees.sum() / max(vegetation.sum(), 1)), 3)
        stats["canopy_height_from_lidar_share"] = round(float(measured.sum() / max(canopy.sum(), 1)), 3)

    canopy = ndi.binary_closing(canopy, structure=np.ones((3, 3), dtype=bool)) & ~(building > 0)
    labels, n = ndi.label(canopy)
    sizes = ndi.sum(canopy, labels, index=np.arange(1, n + 1))
    keep = np.concatenate([[False], sizes >= MIN_CANOPY_PATCH_M2])
    canopy = keep[labels]
    filled = ndi.maximum_filter(height, size=3)
    height = np.where(canopy, np.where(height > 0, height, np.where(filled > 0, filled, DEFAULT_CANOPY_HEIGHT_M)), 0).astype(np.float32)
    stats["patches"] = int(keep.sum())
    return height, stats


def canopy_from_osm_trees(building: NDArray[np.float32], grid: Grid) -> tuple[NDArray[np.float32], dict[str, Any]]:
    """Fallback when no imagery can be fetched: mapped trees as discs, mapped woods as polygons."""
    trees = gpd.read_file(RAW / "trees.geojson")
    shapes: list[Any] = []
    for geom in trees.geometry:
        local = to_local(geom)
        shapes.append(local.buffer(OSM_TREE_CROWN_RADIUS_M) if local.geom_type in ("Point", "LineString") else local)
    mask = rasterio.features.rasterize(((mapping(s), 1) for s in shapes), out_shape=grid.shape, transform=affine_of(grid), fill=0, dtype="uint8")
    canopy = (mask > 0) & ~(building > 0)
    stats = {
        "method": "FALLBACK: OSM natural=tree points as %.1f m discs plus mapped woods, all %.0f m tall" % (OSM_TREE_CROWN_RADIUS_M, DEFAULT_CANOPY_HEIGHT_M),
        "patches": int(len(shapes)),
    }
    return np.where(canopy, DEFAULT_CANOPY_HEIGHT_M, 0).astype(np.float32), stats


def osm_tree_recall(canopy: NDArray[np.float32], grid: Grid) -> dict[str, Any] | None:
    """Of the trees someone mapped by hand in OSM, how many land on or beside segmented canopy."""
    path = RAW / "trees.geojson"
    if not path.exists():
        return None
    trees = gpd.read_file(path)
    points = [to_local(g) for g in trees.geometry if isinstance(g, Point)]
    if not points:
        return None
    near = ndi.binary_dilation(canopy > 0, iterations=3)
    row, col = grid.rowcol(np.array([p.x for p in points]), np.array([p.y for p in points]))
    ok = grid.inside(row, col)
    hits = near[row[ok], col[ok]]
    return {"osm_tree_points": int(ok.sum()), "within_3m_of_canopy": int(hits.sum()), "share": round(float(hits.mean()), 3)}


def vectorize(height: NDArray[np.float32], grid: Grid) -> list[dict[str, Any]]:
    """Canopy patches as simplified polygons with their mean height, for the map and PostGIS."""
    mask = height > 0
    features: list[dict[str, Any]] = []
    labels, n = ndi.label(mask, structure=np.ones((3, 3), dtype=int))
    means = ndi.mean(height, labels, index=np.arange(1, n + 1))
    for geom, value in rasterio.features.shapes(labels.astype(np.int32), mask=mask, transform=affine_of(grid), connectivity=8):
        poly = shape(geom).simplify(0.75, preserve_topology=True)
        if poly.is_empty or poly.area < MIN_CANOPY_PATCH_M2:
            continue
        features.append({
            "type": "Feature",
            "properties": {"h": round(float(means[int(value) - 1]), 1), "area": round(poly.area)},
            "geometry": mapping(to_lonlat(poly, 6)),
        })  # fmt: skip
    return features


def in_pilot(poly: Polygon) -> bool:
    w, s, e, n = PILOT.bbox
    frame = pilot_frame()
    xs, ys = frame.to_xy(np.array([w, e]), np.array([s, n]))
    c = poly.representative_point()
    return bool(xs[0] <= c.x <= xs[1] and ys[0] <= c.y <= ys[1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canopy", choices=["naip", "osm"], default="naip")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    grid = pilot_grid()

    prisms, building_stats = load_prisms()
    building = rasterize_prisms(prisms, grid)
    hag = lidar_height_above_ground()
    if hag is not None:
        building_stats["lidar_cross_check"] = compare_with_lidar(prisms, building, hag, grid)

    if args.canopy == "naip" and (RAW / "naip.npz").exists():
        canopy, canopy_stats = segment_canopy_naip(building, hag)
        canopy_stats["source"] = "naip"
    else:
        canopy, canopy_stats = canopy_from_osm_trees(building, grid)
        canopy_stats["source"] = "osm-fallback"
    canopy_stats["canopy_share_of_grid"] = round(float((canopy > 0).mean()), 4)
    canopy_stats["median_height_m"] = round(float(np.median(canopy[canopy > 0])), 1) if (canopy > 0).any() else None
    canopy_stats["osm_tree_cross_check"] = osm_tree_recall(canopy, grid)

    np.savez_compressed(
        OUT / "rasters.npz",
        building_dm=np.round(building * 10).astype(np.uint16),
        canopy_dm=np.round(canopy * 10).astype(np.uint16),
    )
    write_json_gz(
        OUT / "buildings.geojson.gz",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"id": i, "h": p.height, "src": p.source, "name": p.name, "osm": p.osm, "part": p.part, "pilot": in_pilot(p.polygon)},
                    "geometry": mapping(to_lonlat(p.polygon)),
                }
                for i, p in enumerate(prisms)
            ],
        },
    )
    canopy_features = vectorize(canopy, grid)
    write_json_gz(OUT / "canopy.geojson.gz", {"type": "FeatureCollection", "features": canopy_features})
    canopy_stats["polygons"] = len(canopy_features)

    imagery = json.loads((RAW / "imagery.json").read_text()) if (RAW / "imagery.json").exists() else {}
    stats = {"buildings": building_stats, "canopy": canopy_stats, "imagery": imagery}
    (RAW / "surface_stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps({"buildings": building_stats, "canopy": canopy_stats}, indent=2))


if __name__ == "__main__":
    main()
