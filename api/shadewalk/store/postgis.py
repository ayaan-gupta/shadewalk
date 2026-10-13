"""PostGIS as the system of record for the vector data and the shade table.

Rasters (the height surfaces behind the shadow overlay) and the temperature
climatology stay on disk. Everything else is read from the database, and the
planner's "what is near this street" question is answered by PostGIS itself.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import psycopg

from ..geo import Grid, LocalFrame
from ..network import Network
from ..shade.table import SCALE, ShadeTable
from .base import Dataset, Demand, DemandRadii, Poi
from .files import FILES, read_json_gz, read_pois, read_rasters

SCHEMA = Path(__file__).resolve().parents[3] / "db" / "schema.sql"
TABLES = ["poi_shade", "shade", "sun", "canopy", "buildings", "pois", "segments", "nodes"]

DEMAND_SQL = """
SELECT s.id,
       count(*) FILTER (WHERE p.kind = 'bus_stop'  AND ST_DWithin(s.geom::geography, p.geom::geography, %(bus)s))    AS bus_stops,
       count(*) FILTER (WHERE p.kind = 'rail_stop' AND ST_DWithin(s.geom::geography, p.geom::geography, %(rail)s))   AS rail_stops,
       count(*) FILTER (WHERE p.kind = 'school'    AND ST_DWithin(s.geom::geography, p.geom::geography, %(school)s)) AS schools
FROM segments s
LEFT JOIN pois p
       ON p.kind IN ('bus_stop', 'rail_stop', 'school')
      AND ST_DWithin(s.geom::geography, p.geom::geography, %(widest)s)
GROUP BY s.id
ORDER BY s.id
"""


def fingerprint(data_dir: Path) -> str:
    digest = hashlib.sha256()
    for name in FILES:
        digest.update(name.encode())
        digest.update((data_dir / name).read_bytes())
    return digest.hexdigest()


def connect(url: str, attempts: int = 30) -> psycopg.Connection[tuple[Any, ...]]:
    """Connect, waiting out a container that is still starting."""
    last: Exception | None = None
    for _ in range(attempts):
        try:
            return psycopg.connect(url, connect_timeout=3)
        except psycopg.OperationalError as exc:
            last = exc
            time.sleep(1)
    raise RuntimeError(f"PostGIS is not reachable: {last}")


def wkt_line(coords: list[list[float]]) -> str:
    return "SRID=4326;LINESTRING(" + ",".join(f"{x} {y}" for x, y in coords) + ")"


def wkt_polygon(rings: list[list[list[float]]]) -> str:
    return "SRID=4326;POLYGON(" + ",".join("(" + ",".join(f"{x} {y}" for x, y in ring) + ")" for ring in rings) + ")"


def seed(url: str, data_dir: Path, force: bool = False) -> bool:
    """Load the committed dataset into PostGIS. Returns False when it was already current."""
    mark = fingerprint(data_dir)
    with connect(url) as conn, conn.cursor() as cur:
        cur.execute(SCHEMA.read_text())
        cur.execute("SELECT value FROM dataset WHERE key = 'fingerprint'")
        row = cur.fetchone()
        if row and row[0] == mark and not force:
            return False
        cur.execute("TRUNCATE " + ", ".join(TABLES) + " CASCADE")

        network = read_json_gz(data_dir / "network.json.gz")
        with cur.copy("COPY nodes (id, geom) FROM STDIN") as copy:
            for i, (lon, lat) in enumerate(network["nodes"]):
                copy.write_row((i, f"SRID=4326;POINT({lon} {lat})"))
        with cur.copy("COPY segments (id, u, v, length_m, kind, name, street, covered, geom) FROM STDIN") as copy:
            for e in network["edges"]:
                copy.write_row((e["id"], e["u"], e["v"], e["length_m"], e["kind"], e.get("name"), e.get("street"), e["covered"], wkt_line(e["coords"])))

        pois = read_pois(data_dir)
        with cur.copy("COPY pois (id, kind, name, osm, geom) FROM STDIN") as copy:
            for p in pois:
                copy.write_row((p.id, p.kind, p.name, p.osm, f"SRID=4326;POINT({p.lon} {p.lat})"))

        table = ShadeTable.load(data_dir / "shade.npz")
        for name, key, both in (("shade", "segment_id", (table.segments_all, table.segments_buildings)), ("poi_shade", "poi_id", (table.pois_all, table.pois_buildings))):
            with cur.copy(f"COPY {name} (month, hour, {key}, shade_all, shade_buildings) FROM STDIN") as copy:
                everything, buildings = both
                ids = range(everything.shape[2])
                for month in range(12):
                    for hour in range(24):
                        a, b = everything[month, hour].tolist(), buildings[month, hour].tolist()
                        for i in ids:
                            copy.write_row((month + 1, hour, i, a[i], b[i]))
        with cur.copy("COPY sun (month, slot, azimuth, elevation) FROM STDIN") as copy:
            for month in range(12):
                for slot in range(table.sun_azimuth.shape[1]):
                    copy.write_row((month + 1, slot, float(table.sun_azimuth[month, slot]), float(table.sun_elevation[month, slot])))

        with cur.copy("COPY buildings (id, height_m, height_source, name, osm, part, in_pilot, geom) FROM STDIN") as copy:
            for f in read_json_gz(data_dir / "buildings.geojson.gz")["features"]:
                p = f["properties"]
                copy.write_row((p["id"], p["h"], p["src"], p.get("name"), p["osm"], p["part"], p["pilot"], wkt_polygon(f["geometry"]["coordinates"])))
        with cur.copy("COPY canopy (id, height_m, area_m2, geom) FROM STDIN") as copy:
            for i, f in enumerate(read_json_gz(data_dir / "canopy.geojson.gz")["features"]):
                copy.write_row((i, f["properties"]["h"], f["properties"]["area"], wkt_polygon(f["geometry"]["coordinates"])))

        meta = json.loads((data_dir / "meta.json").read_text())
        cur.execute(
            "INSERT INTO dataset (key, value) VALUES ('fingerprint', %s), ('meta', %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (json.dumps(mark), json.dumps(meta)),
        )
        cur.execute("ANALYZE")
    return True


class PostgisStore:
    name = "postgis"

    def __init__(self, url: str, data_dir: Path) -> None:
        self.url = url
        self.data_dir = data_dir

    def load(self) -> Dataset:
        seed(self.url, self.data_dir)
        with connect(self.url) as conn, conn.cursor() as cur:
            cur.execute("SELECT value FROM dataset WHERE key = 'meta'")
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("database has no dataset loaded")
            meta: dict[str, Any] = row[0]
            frame = LocalFrame(lat0=meta["frame"]["lat0"], lon0=meta["frame"]["lon0"])

            cur.execute("SELECT ST_X(geom), ST_Y(geom) FROM nodes ORDER BY id")
            nodes = [[float(x), float(y)] for x, y in cur.fetchall()]
            cur.execute("SELECT id, u, v, length_m, kind, name, street, covered, ST_AsGeoJSON(geom, 7) FROM segments ORDER BY id")
            edges = [
                {"id": i, "u": u, "v": v, "length_m": length, "kind": kind, "name": name, "street": street, "covered": covered, "coords": json.loads(geo)["coordinates"]}
                for i, u, v, length, kind, name, street, covered, geo in cur.fetchall()
            ]
            cur.execute("SELECT id, kind, name, ST_X(geom), ST_Y(geom), osm FROM pois ORDER BY id")
            pois = [Poi(id=i, kind=k, name=n, lon=float(x), lat=float(y), osm=o) for i, k, n, x, y, o in cur.fetchall()]

            def table(name: str, key: str, count: int) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
                cur.execute(f"SELECT shade_all, shade_buildings FROM {name} ORDER BY month, hour, {key}")
                both = np.array(cur.fetchall(), dtype=np.uint8)
                if both.shape[0] != 12 * 24 * count:
                    raise RuntimeError(f"{name} has {both.shape[0]} rows, expected {12 * 24 * count}")
                return both[:, 0].reshape(12, 24, count), both[:, 1].reshape(12, 24, count)

            seg_all, seg_buildings = table("shade", "segment_id", len(edges))
            poi_all, poi_buildings = table("poi_shade", "poi_id", len(pois))
            cur.execute("SELECT azimuth, elevation FROM sun ORDER BY month, slot")
            sun = np.array(cur.fetchall(), dtype=np.float32)
            slots = sun.shape[0] // 12

            cur.execute(
                "SELECT json_build_object('type', 'FeatureCollection', 'features', coalesce(json_agg(json_build_object("
                "'type', 'Feature', 'properties', json_build_object('id', id, 'h', height_m, 'src', height_source, 'name', name, 'osm', osm, 'part', part, 'pilot', in_pilot),"
                "'geometry', ST_AsGeoJSON(geom, 7)::json) ORDER BY id), '[]'::json)) FROM buildings"
            )
            buildings = cur.fetchone()[0]  # type: ignore[index]
            cur.execute(
                "SELECT json_build_object('type', 'FeatureCollection', 'features', coalesce(json_agg(json_build_object("
                "'type', 'Feature', 'properties', json_build_object('h', height_m, 'area', area_m2),"
                "'geometry', ST_AsGeoJSON(geom, 6)::json) ORDER BY id), '[]'::json)) FROM canopy"
            )
            canopy = cur.fetchone()[0]  # type: ignore[index]

        building_height, canopy_height = read_rasters(self.data_dir)
        return Dataset(
            meta=meta,
            frame=frame,
            grid=Grid.from_dict(meta["grid"]),
            network=Network.build(frame, nodes, edges),
            shade=ShadeTable(
                segments_all=seg_all,
                segments_buildings=seg_buildings,
                pois_all=poi_all,
                pois_buildings=poi_buildings,
                sun_azimuth=sun[:, 0].reshape(12, slots),
                sun_elevation=sun[:, 1].reshape(12, slots),
            ),
            pois=pois,
            buildings=buildings,
            canopy=canopy,
            building_height=building_height,
            canopy_height=canopy_height,
        )

    def demand(self, radii: DemandRadii) -> Demand:
        with connect(self.url) as conn, conn.cursor() as cur:
            cur.execute(
                DEMAND_SQL,
                {"bus": radii.bus_stop, "rail": radii.rail_stop, "school": radii.school, "widest": max(radii.bus_stop, radii.rail_stop, radii.school)},
            )
            rows = np.array(cur.fetchall(), dtype=np.int64)
        return Demand(bus_stops=rows[:, 1], rail_stops=rows[:, 2], schools=rows[:, 3])


def shade_scale() -> int:
    return SCALE
