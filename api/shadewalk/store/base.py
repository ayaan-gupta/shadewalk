"""What the API needs from storage, and the dataset it gets back."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from ..geo import Grid, LocalFrame
from ..network import Network
from ..shade.table import ShadeTable


@dataclass(frozen=True)
class Poi:
    id: int
    kind: str
    name: str | None
    lon: float
    lat: float
    osm: str


@dataclass(frozen=True)
class DemandRadii:
    """How close a foot-traffic indicator has to be to count toward a segment, in metres."""

    bus_stop: float = 40.0
    rail_stop: float = 80.0
    school: float = 150.0


@dataclass(frozen=True)
class Demand:
    """Per-segment counts of nearby foot-traffic indicators."""

    bus_stops: NDArray[np.int64]
    rail_stops: NDArray[np.int64]
    schools: NDArray[np.int64]


@dataclass
class Dataset:
    meta: dict[str, Any]
    frame: LocalFrame
    grid: Grid
    network: Network
    shade: ShadeTable
    pois: list[Poi]
    buildings: dict[str, Any]
    canopy: dict[str, Any]
    building_height: NDArray[np.float32]
    canopy_height: NDArray[np.float32]

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        w, s, e, n = self.meta["bbox"]
        return (float(w), float(s), float(e), float(n))


class Store(Protocol):
    name: str

    def load(self) -> Dataset:
        """Everything the API keeps in memory."""
        ...

    def demand(self, radii: DemandRadii) -> Demand:
        """Count bus stops, rail stops and schools near every segment."""
        ...
