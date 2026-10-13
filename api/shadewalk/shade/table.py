"""The precomputed shade table and the sun table that goes with it.

Shade fractions are stored as bytes, 0 to SCALE, for [month, hour, segment].
A request for 15:20 blends the 15:00 and 16:00 rows. The sun table is finer
(every 15 minutes) because the shadow overlay on the map is drawn on demand.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from numpy.typing import NDArray

SCALE = 250
Layer = Literal["all", "buildings"]


@dataclass(frozen=True)
class Sun:
    azimuth_deg: float
    elevation_deg: float

    @property
    def up(self) -> bool:
        return self.elevation_deg > 0


@dataclass(frozen=True)
class ShadeTable:
    segments_all: NDArray[np.uint8]
    segments_buildings: NDArray[np.uint8]
    pois_all: NDArray[np.uint8]
    pois_buildings: NDArray[np.uint8]
    sun_azimuth: NDArray[np.float32]
    sun_elevation: NDArray[np.float32]

    @staticmethod
    def load(path: Path) -> "ShadeTable":
        with np.load(path) as data:
            return ShadeTable(
                segments_all=data["segments_all"],
                segments_buildings=data["segments_buildings"],
                pois_all=data["pois_all"],
                pois_buildings=data["pois_buildings"],
                sun_azimuth=data["sun_azimuth"].astype(np.float32),
                sun_elevation=data["sun_elevation"].astype(np.float32),
            )

    @property
    def segment_count(self) -> int:
        return int(self.segments_all.shape[2])

    @property
    def sun_slot_minutes(self) -> int:
        return 24 * 60 // int(self.sun_azimuth.shape[1])

    def _blend(self, table: NDArray[np.uint8], month: int, minute: float) -> NDArray[np.float32]:
        check_month(month)
        minute = float(np.clip(minute, 0, 24 * 60 - 1e-6))
        hour = int(minute // 60)
        weight = (minute - hour * 60) / 60
        here = table[month - 1, hour].astype(np.float32)
        if weight == 0:
            return here / SCALE
        there = table[month - 1, (hour + 1) % 24].astype(np.float32)
        return (here * (1 - weight) + there * weight) / SCALE

    def segments(self, month: int, minute: float, layer: Layer = "all") -> NDArray[np.float32]:
        """Shade fraction of every segment, 0 to 1, for a month (1 to 12) and minute of the local day."""
        return self._blend(self.segments_all if layer == "all" else self.segments_buildings, month, minute)

    def pois(self, month: int, minute: float, layer: Layer = "all") -> NDArray[np.float32]:
        return self._blend(self.pois_all if layer == "all" else self.pois_buildings, month, minute)

    def sun(self, month: int, minute: float) -> Sun:
        """Sun position, linearly interpolated between table slots (azimuth along the short arc)."""
        check_month(month)
        slot_minutes = self.sun_slot_minutes
        slots = self.sun_azimuth.shape[1]
        position = float(np.clip(minute, 0, 24 * 60 - 1e-6)) / slot_minutes
        i = int(position)
        w = position - i
        j = min(i + 1, slots - 1)
        az0, az1 = float(self.sun_azimuth[month - 1, i]), float(self.sun_azimuth[month - 1, j])
        delta = (az1 - az0 + 180) % 360 - 180
        el0, el1 = float(self.sun_elevation[month - 1, i]), float(self.sun_elevation[month - 1, j])
        return Sun(azimuth_deg=(az0 + w * delta) % 360, elevation_deg=el0 + w * (el1 - el0))

    def daylight_minutes(self, month: int) -> tuple[int, int]:
        """First and last table slot of the month's representative day with the sun above the horizon."""
        check_month(month)
        up = np.flatnonzero(self.sun_elevation[month - 1] > 0)
        step = self.sun_slot_minutes
        return (int(up[0]) * step, int(up[-1]) * step) if len(up) else (0, 0)


def check_month(month: int) -> None:
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1 to 12, got {month}")
