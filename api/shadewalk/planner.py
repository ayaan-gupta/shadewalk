"""The planner view: which blocks are both sunny and busy, and which bus stops have no shade.

A block's priority is its sun exposure in the chosen window times its foot
traffic indicators (bus stops, rail stops and schools nearby). It is a ranking
aid for where shade would help the most people, not a count of pedestrians.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .network import Network
from .shade.table import Layer, ShadeTable
from .store.base import Demand, Poi

# Blocks where a tree or a shelter could actually go.
PLANTABLE_KINDS = {"sidewalk", "path", "street"}
MIN_BLOCK_LENGTH_M = 20.0
WEIGHT_BUS, WEIGHT_RAIL, WEIGHT_SCHOOL = 1.0, 2.0, 3.0


@dataclass(frozen=True)
class Block:
    segment_id: int
    street: str | None
    kind: str
    length_m: float
    shade: float
    bus_stops: int
    rail_stops: int
    schools: int
    demand: float
    priority: float


@dataclass(frozen=True)
class StopShade:
    poi: Poi
    shade: float


@dataclass(frozen=True)
class PlannerResult:
    blocks: list[Block]
    stops: list[StopShade]
    network_shade: float
    low_shade_km: float
    unshaded_stops: int
    stop_count: int


def window_mean(table: ShadeTable, month: int, start_hour: int, end_hour: int, layer: Layer, what: str) -> NDArray[np.float32]:
    """Mean shade over the whole hours start..end inclusive."""
    if not 0 <= start_hour <= end_hour <= 23:
        raise ValueError("hours must satisfy 0 <= start <= end <= 23")
    rows = [table.segments(month, h * 60, layer) if what == "segments" else table.pois(month, h * 60, layer) for h in range(start_hour, end_hour + 1)]
    out: NDArray[np.float32] = np.mean(rows, axis=0)
    return out


def rank(
    network: Network,
    table: ShadeTable,
    pois: list[Poi],
    demand: Demand,
    month: int,
    start_hour: int,
    end_hour: int,
    layer: Layer = "all",
    limit: int = 40,
) -> PlannerResult:
    shade = window_mean(table, month, start_hour, end_hour, layer, "segments")
    weight = WEIGHT_BUS * demand.bus_stops + WEIGHT_RAIL * demand.rail_stops + WEIGHT_SCHOOL * demand.schools
    plantable = np.array([e.kind in PLANTABLE_KINDS and e.length_m >= MIN_BLOCK_LENGTH_M and not e.covered for e in network.edges])
    priority = np.where(plantable, (1.0 - shade) * weight, 0.0)
    order = np.lexsort((np.arange(network.edge_count), -network.lengths, -priority))
    blocks = [
        Block(
            segment_id=int(i),
            street=network.edges[i].street,
            kind=network.edges[i].kind,
            length_m=network.edges[i].length_m,
            shade=float(shade[i]),
            bus_stops=int(demand.bus_stops[i]),
            rail_stops=int(demand.rail_stops[i]),
            schools=int(demand.schools[i]),
            demand=float(weight[i]),
            priority=float(priority[i]),
        )
        for i in order[:limit]
        if priority[i] > 0
    ]

    poi_shade = window_mean(table, month, start_hour, end_hour, layer, "pois")
    waits = [StopShade(poi=p, shade=float(poi_shade[p.id])) for p in pois if p.kind in ("bus_stop", "rail_stop")]
    waits.sort(key=lambda s: (s.shade, s.poi.id))
    lengths = network.lengths
    return PlannerResult(
        blocks=blocks,
        stops=waits,
        network_shade=float((shade * lengths).sum() / lengths.sum()),
        low_shade_km=float(lengths[shade < 0.2].sum() / 1000),
        unshaded_stops=sum(1 for s in waits if s.shade < 0.1),
        stop_count=len(waits),
    )
