"""The walking graph held in memory for routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .geo import FloatArray, LocalFrame


@dataclass(frozen=True)
class Edge:
    id: int
    u: int
    v: int
    length_m: float
    kind: str
    name: str | None
    street: str | None
    covered: bool
    # [[lon, lat], ...] running from node u to node v
    coords: list[list[float]]


@dataclass
class Network:
    frame: LocalFrame
    node_lon: FloatArray
    node_lat: FloatArray
    node_x: FloatArray
    node_y: FloatArray
    edges: list[Edge]
    lengths: FloatArray
    # adjacency[node] = [(neighbour, edge id), ...]
    adjacency: list[list[tuple[int, int]]] = field(repr=False)

    @property
    def node_count(self) -> int:
        return len(self.node_lon)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    @staticmethod
    def build(frame: LocalFrame, nodes: list[list[float]], edges: list[dict[str, Any]]) -> Network:
        lon = np.array([n[0] for n in nodes], dtype=np.float64)
        lat = np.array([n[1] for n in nodes], dtype=np.float64)
        x, y = frame.to_xy(lon, lat)
        parsed = [
            Edge(
                id=int(e["id"]),
                u=int(e["u"]),
                v=int(e["v"]),
                length_m=float(e["length_m"]),
                kind=str(e["kind"]),
                name=e.get("name"),
                street=e.get("street"),
                covered=bool(e.get("covered", False)),
                coords=e["coords"],
            )
            for e in edges
        ]
        if [e.id for e in parsed] != list(range(len(parsed))):
            raise ValueError("edge ids must be 0..n-1 in order: the shade table is indexed by them")
        adjacency: list[list[tuple[int, int]]] = [[] for _ in nodes]
        for e in parsed:
            adjacency[e.u].append((e.v, e.id))
            adjacency[e.v].append((e.u, e.id))
        return Network(
            frame=frame,
            node_lon=lon,
            node_lat=lat,
            node_x=x,
            node_y=y,
            edges=parsed,
            lengths=np.array([e.length_m for e in parsed], dtype=np.float64),
            adjacency=adjacency,
        )

    def nearest_node(self, lon: float, lat: float) -> tuple[int, float]:
        """The closest graph node and its distance in metres."""
        x, y = self.frame.to_xy(lon, lat)
        d2 = (self.node_x - float(x)) ** 2 + (self.node_y - float(y)) ** 2
        i = int(np.argmin(d2))
        return i, float(np.sqrt(d2[i]))

    def midpoints(self) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Lon, lat of the vertex nearest the middle of each edge. Good enough for labels and markers."""
        lon = np.array([e.coords[len(e.coords) // 2][0] if len(e.coords) > 2 else (e.coords[0][0] + e.coords[-1][0]) / 2 for e in self.edges])
        lat = np.array([e.coords[len(e.coords) // 2][1] if len(e.coords) > 2 else (e.coords[0][1] + e.coords[-1][1]) / 2 for e in self.edges])
        return lon, lat
