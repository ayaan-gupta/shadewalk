"""The committed pilot dataset read straight from disk. No database, no network."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from ..geo import Grid, LocalFrame
from ..network import Network
from ..shade.table import ShadeTable
from .base import Dataset, Demand, DemandRadii, Poi

FILES = ["meta.json", "network.json.gz", "pois.json", "shade.npz", "rasters.npz", "buildings.geojson.gz", "canopy.geojson.gz", "climatology.json"]


def read_json_gz(path: Path) -> Any:
    with gzip.open(path, "rb") as fh:
        return json.loads(fh.read())


def read_rasters(data_dir: Path) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    with np.load(data_dir / "rasters.npz") as data:
        return data["building_dm"].astype(np.float32) / 10, data["canopy_dm"].astype(np.float32) / 10


def read_pois(data_dir: Path) -> list[Poi]:
    return [Poi(id=p["id"], kind=p["kind"], name=p.get("name"), lon=p["lon"], lat=p["lat"], osm=p["osm"]) for p in json.loads((data_dir / "pois.json").read_text())]


def point_to_polyline_m(px: float, py: float, xs: NDArray[np.float64], ys: NDArray[np.float64]) -> float:
    """Shortest distance from a point to a polyline, all in local metres."""
    ax, ay, bx, by = xs[:-1], ys[:-1], xs[1:], ys[1:]
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / np.where(length2 > 0, length2, 1), 0, 1)
    return float(np.sqrt(((ax + t * dx - px) ** 2 + (ay + t * dy - py) ** 2).min()))


class FileStore:
    name = "files"

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self._dataset: Dataset | None = None

    def load(self) -> Dataset:
        missing = [f for f in FILES if not (self.data_dir / f).exists()]
        if missing:
            raise FileNotFoundError(f"pilot dataset incomplete in {self.data_dir}: missing {', '.join(missing)}")
        meta = json.loads((self.data_dir / "meta.json").read_text())
        frame = LocalFrame(lat0=meta["frame"]["lat0"], lon0=meta["frame"]["lon0"])
        raw = read_json_gz(self.data_dir / "network.json.gz")
        building, canopy = read_rasters(self.data_dir)
        self._dataset = Dataset(
            meta=meta,
            frame=frame,
            grid=Grid.from_dict(meta["grid"]),
            network=Network.build(frame, raw["nodes"], raw["edges"]),
            shade=ShadeTable.load(self.data_dir / "shade.npz"),
            pois=read_pois(self.data_dir),
            buildings=read_json_gz(self.data_dir / "buildings.geojson.gz"),
            canopy=read_json_gz(self.data_dir / "canopy.geojson.gz"),
            building_height=building,
            canopy_height=canopy,
        )
        return self._dataset

    def demand(self, radii: DemandRadii) -> Demand:
        data = self._dataset or self.load()
        return count_demand(data.network, data.pois, radii)


def count_demand(network: Network, pois: list[Poi], radii: DemandRadii) -> Demand:
    """The in-memory twin of the PostGIS ST_DWithin join in store/postgis.py."""
    frame = network.frame
    shapes = []
    for edge in network.edges:
        coords = np.array(edge.coords)
        shapes.append(frame.to_xy(coords[:, 0], coords[:, 1]))
    counts = {kind: np.zeros(network.edge_count, dtype=np.int64) for kind in ("bus_stop", "rail_stop", "school")}
    limits = {"bus_stop": radii.bus_stop, "rail_stop": radii.rail_stop, "school": radii.school}
    mid_x = np.array([xs.mean() for xs, _ in shapes])
    mid_y = np.array([ys.mean() for _, ys in shapes])
    reach = np.array([float(np.hypot(xs - xs.mean(), ys - ys.mean()).max()) for xs, ys in shapes])
    for poi in pois:
        if poi.kind not in counts:
            continue
        px, py = (float(v) for v in frame.to_xy(poi.lon, poi.lat))
        limit = limits[poi.kind]
        for i in np.flatnonzero(np.hypot(mid_x - px, mid_y - py) <= limit + reach):
            if point_to_polyline_m(px, py, *shapes[i]) <= limit:
                counts[poi.kind][i] += 1
    return Demand(bus_stops=counts["bus_stop"], rail_stops=counts["rail_stop"], schools=counts["school"])
