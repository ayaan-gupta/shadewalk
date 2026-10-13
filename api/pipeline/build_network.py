"""Step 3. Turn the raw OSM pull into the walking graph and the points of interest.

    python -m pipeline.build_network
"""

from __future__ import annotations

import ast
import json
import warnings
from typing import Any

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from shapely import STRtree
from shapely.geometry import LineString, Point

from shadewalk.geo import polyline_length

from .config import OUT, PILOT, RAW
from .grid import pilot_frame
from .io import write_json_gz

# A sidewalk with no name of its own borrows the name of a road this close to it.
STREET_LABEL_RADIUS_M = 30.0


def values(raw: Any) -> list[str]:
    """osmnx joins the tags of merged ways into a list, and GraphML stores that list as its repr."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return []
    if isinstance(raw, list):
        return [str(v) for v in raw]
    text = str(raw)
    if text.startswith("["):
        try:
            return [str(v) for v in ast.literal_eval(text)]
        except (ValueError, SyntaxError):
            return [text]
    return [text]


def lowest_level(raw: Any) -> float:
    lows: list[float] = []
    for item in values(raw):
        for part in item.replace(",", ";").split(";"):
            try:
                lows.append(float(part))
            except ValueError:
                continue
    return min(lows) if lows else 0.0


def walkable_outdoors(tags: dict[str, Any]) -> bool:
    """Indoor routing is out of scope, and so are tunnels and anything signed as closed."""
    if "corridor" in values(tags.get("highway")):
        return False
    if "yes" in values(tags.get("indoor")):
        return False
    if "yes" in values(tags.get("tunnel")):
        return False
    if set(values(tags.get("access"))) & {"no", "private"}:
        return False
    return lowest_level(tags.get("layer")) >= 0 and lowest_level(tags.get("level")) >= 0


def classify(tags: dict[str, Any]) -> str:
    highway, footway = values(tags.get("highway")), values(tags.get("footway"))
    if "steps" in highway:
        return "steps"
    if "crossing" in footway and "sidewalk" not in footway:
        return "crossing"
    if "sidewalk" in footway:
        return "sidewalk"
    if set(highway) & {"footway", "path", "pedestrian"}:
        return "path"
    if "service" in highway:
        return "service"
    return "street"


def build_graph() -> tuple[list[list[float]], list[dict[str, Any]], dict[str, int]]:
    frame = pilot_frame()
    graph = ox.convert.to_undirected(ox.load_graphml(RAW / "walk.graphml"))
    stats = {"raw_nodes": graph.number_of_nodes(), "raw_edges": graph.number_of_edges()}

    kept = nx.MultiGraph()
    kept.add_nodes_from(graph.nodes(data=True))
    for u, v, key, data in graph.edges(keys=True, data=True):
        if u != v and walkable_outdoors(data):
            kept.add_edge(u, v, key, **data)
    stats["dropped_indoor_tunnel_private"] = stats["raw_edges"] - kept.number_of_edges()
    main = max(nx.connected_components(kept), key=len)
    stats["dropped_disconnected_nodes"] = kept.number_of_nodes() - len(main)
    kept = kept.subgraph(main)

    ids = sorted(kept.nodes)
    index = {osm: i for i, osm in enumerate(ids)}
    nodes = [[round(float(kept.nodes[n]["x"]), 7), round(float(kept.nodes[n]["y"]), 7)] for n in ids]

    edges: list[dict[str, Any]] = []
    for u, v, data in kept.edges(data=True):
        geom = data.get("geometry")
        if geom is None:
            coords = [nodes[index[u]], nodes[index[v]]]
        else:
            coords = [[round(x, 7), round(y, 7)] for x, y in geom.coords]
            start = np.array(nodes[index[u]])
            if np.hypot(*(np.array(coords[0]) - start)) > np.hypot(*(np.array(coords[-1]) - start)):
                coords.reverse()
        a, b = index[u], index[v]
        if a > b:
            a, b = b, a
            coords = coords[::-1]
        xs, ys = frame.to_xy([c[0] for c in coords], [c[1] for c in coords])
        names = values(data.get("name"))
        edges.append({
            "u": a,
            "v": b,
            "length_m": round(polyline_length(xs, ys), 2),
            "kind": classify(data),
            "name": names[0] if names else None,
            "covered": bool("yes" in values(data.get("covered")) or "building_passage" in values(data.get("tunnel"))),
            "coords": coords,
        })  # fmt: skip
    edges.sort(key=lambda e: (e["u"], e["v"], e["length_m"], e["coords"][1]))
    stats["nodes"] = len(nodes)
    stats["edges"] = len(edges)
    return nodes, edges, stats


def label_streets(edges: list[dict[str, Any]]) -> int:
    """Give every edge a `street`: its own name, else the nearest named road."""
    frame = pilot_frame()
    roads = gpd.read_file(RAW / "roads.geojson")
    roads = roads[roads["name"].notna()]
    lines: list[LineString] = []
    names: list[str] = []
    for geom, name in zip(roads.geometry, roads["name"]):
        for part in getattr(geom, "geoms", [geom]):
            xs, ys = frame.to_xy(*np.array(part.coords).T[:2])
            lines.append(LineString(np.column_stack([xs, ys])))
            names.append(str(name))
    tree = STRtree(lines)
    labelled = 0
    for edge in edges:
        if edge["name"]:
            edge["street"] = edge["name"]
            labelled += 1
            continue
        xs, ys = frame.to_xy([c[0] for c in edge["coords"]], [c[1] for c in edge["coords"]])
        mid = LineString(np.column_stack([xs, ys])).interpolate(0.5, normalized=True)
        hit = tree.query_nearest(mid, max_distance=STREET_LABEL_RADIUS_M, return_distance=False)
        edge["street"] = names[int(hit[0])] if len(hit) else None
        labelled += edge["street"] is not None
    return labelled


POI_KINDS: list[tuple[str, str, set[str]]] = [
    ("highway", "bus_stop", {"bus_stop"}),
    ("railway", "rail_stop", {"station", "tram_stop"}),
    ("amenity", "school", {"school", "kindergarten", "college", "university"}),
    ("amenity", "water", {"drinking_water"}),
    ("amenity", "cooling", {"library", "community_centre"}),
    ("tourism", "cooling", {"museum"}),
    ("leisure", "park", {"park"}),
    ("tourism", "landmark", {"attraction"}),
]


def build_pois() -> list[dict[str, Any]]:
    """Bus stops, rail stops, schools, drinking water, public indoor places and parks."""
    raw = gpd.read_file(RAW / "pois.geojson")
    w, s, e, n = PILOT.bbox
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float, float]] = set()
    for _, row in raw.iterrows():
        kind = next((k for col, k, vals in POI_KINDS if col in raw.columns and row.get(col) in vals), None)
        if kind is None:
            continue
        point: Point = row.geometry if row.geometry.geom_type == "Point" else row.geometry.representative_point()
        if not (w <= point.x <= e and s <= point.y <= n):
            continue
        name = row.get("name") if isinstance(row.get("name"), str) else None
        key = (kind, name or "", round(point.x, 4), round(point.y, 4))
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": kind, "name": name, "lon": round(point.x, 7), "lat": round(point.y, 7), "osm": f"{row['element']}/{row['id']}"})
    out.sort(key=lambda p: (p["kind"], p["lat"], p["lon"]))
    for i, poi in enumerate(out):
        poi["id"] = i
    return out


def main() -> None:
    warnings.filterwarnings("ignore", category=FutureWarning)
    OUT.mkdir(parents=True, exist_ok=True)
    nodes, edges, stats = build_graph()
    stats["edges_with_street_label"] = label_streets(edges)
    for i, edge in enumerate(edges):
        edge["id"] = i
    total_km = sum(e["length_m"] for e in edges) / 1000
    stats["length_km"] = round(total_km, 2)
    by_kind: dict[str, float] = {}
    for e in edges:
        by_kind[e["kind"]] = by_kind.get(e["kind"], 0.0) + e["length_m"] / 1000
    stats_out = {**stats, "km_by_kind": {k: round(v, 2) for k, v in sorted(by_kind.items())}}
    write_json_gz(OUT / "network.json.gz", {"nodes": nodes, "edges": edges})
    pois = build_pois()
    (OUT / "pois.json").write_text(json.dumps(pois, separators=(",", ":")) + "\n")
    counts: dict[str, int] = {}
    for p in pois:
        counts[p["kind"]] = counts.get(p["kind"], 0) + 1
    (RAW / "network_stats.json").write_text(json.dumps({"network": stats_out, "pois": counts}, indent=2))
    print(json.dumps({"network": stats_out, "pois": counts}, indent=2))


if __name__ == "__main__":
    main()
