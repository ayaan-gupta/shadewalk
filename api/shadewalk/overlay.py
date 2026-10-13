"""The shadow layer for the map: one small PNG per sun position, drawn from the model itself.

What the user sees sweeping across the streets is the same mask the shade table
was computed from, cropped to the walking area. It is a picture of data, not a
generated tile.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock

import numpy as np
from numpy.typing import NDArray

from .geo import Grid, LocalFrame
from .png import encode_indexed
from .shade.raster import cast_shadow
from .shade.table import Layer, ShadeTable

# palette index -> (r, g, b, a). Cool teal shade and a greener teal under tree crowns.
PALETTE = [(0, 0, 0, 0), (14, 92, 104, 120), (20, 120, 96, 150)]
NIGHT = [(16, 44, 60, 110)]
MIN_SUN_ELEVATION_DEG = 2.0


@dataclass
class ShadowOverlay:
    frame: LocalFrame
    grid: Grid
    building: NDArray[np.float32]
    canopy: NDArray[np.float32]
    # west, south, east, north of the walking area
    bbox: tuple[float, float, float, float]
    table: ShadeTable
    max_cached: int = 400
    _cache: "OrderedDict[tuple[int, int, str], bytes]" = field(default_factory=OrderedDict, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def _window(self) -> tuple[slice, slice]:
        w, s, e, n = self.bbox
        xs, ys = self.frame.to_xy(np.array([w, e]), np.array([s, n]))
        rows, cols = self.grid.rowcol(xs, ys[::-1])
        return slice(int(rows[0]), int(rows[1])), slice(int(cols[0]), int(cols[1]))

    def corners(self) -> list[list[float]]:
        """Lon, lat of the image corners in MapLibre's order: top-left, top-right, bottom-right, bottom-left."""
        rows, cols = self._window()
        x0 = self.grid.x_min + cols.start * self.grid.res
        x1 = self.grid.x_min + cols.stop * self.grid.res
        y1 = self.grid.y_max - rows.start * self.grid.res
        y0 = self.grid.y_max - rows.stop * self.grid.res
        lon, lat = self.frame.to_lonlat(np.array([x0, x1, x1, x0]), np.array([y1, y1, y0, y0]))
        return [[round(float(a), 7), round(float(b), 7)] for a, b in zip(lon, lat)]

    def render(self, month: int, minute: int, layer: Layer = "all") -> bytes:
        key = (month, minute, layer)
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit
        png = self._draw(month, minute, layer)
        with self._lock:
            self._cache[key] = png
            while len(self._cache) > self.max_cached:
                self._cache.popitem(last=False)
        return png

    def _draw(self, month: int, minute: int, layer: Layer) -> bytes:
        rows, cols = self._window()
        sun = self.table.sun(month, minute)
        shape = (rows.stop - rows.start, cols.stop - cols.start)
        if sun.elevation_deg < MIN_SUN_ELEVATION_DEG:
            return encode_indexed(np.zeros(shape, dtype=np.uint8), NIGHT)
        height = np.maximum(self.building, self.canopy) if layer == "all" else self.building
        shadow = cast_shadow(height, self.grid, sun.azimuth_deg, sun.elevation_deg).to_grid()[rows, cols]
        roof = self.building[rows, cols] > 0
        index = np.where(shadow & ~roof, 1, 0).astype(np.uint8)
        if layer == "all":
            index[(self.canopy[rows, cols] > 0) & ~roof] = 2
        return encode_indexed(index, PALETTE)
