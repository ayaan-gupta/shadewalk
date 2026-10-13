"""A local metric frame for the pilot area, and the raster grid laid over it.

The pilot is under 3 km across, so a tangent plane at its centre is accurate
to a few centimetres and has two properties a UTM zone does not: +y is true
north (sun azimuths need no grid-convergence correction) and the grid is
axis-aligned with longitude and latitude (a raster drops onto a web map with
four corner coordinates).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class LocalFrame:
    """East/north metres from (lat0, lon0) using the ellipsoid's radii of curvature there."""

    lat0: float
    lon0: float

    @property
    def metres_per_degree(self) -> tuple[float, float]:
        """(metres per degree of longitude, metres per degree of latitude) at the origin."""
        phi = math.radians(self.lat0)
        s2 = math.sin(phi) ** 2
        prime_vertical = WGS84_A / math.sqrt(1 - WGS84_E2 * s2)
        meridional = WGS84_A * (1 - WGS84_E2) / (1 - WGS84_E2 * s2) ** 1.5
        return (
            math.radians(1) * prime_vertical * math.cos(phi),
            math.radians(1) * meridional,
        )

    def to_xy(self, lon: ArrayLike, lat: ArrayLike) -> tuple[FloatArray, FloatArray]:
        mx, my = self.metres_per_degree
        return (
            (np.asarray(lon, dtype=np.float64) - self.lon0) * mx,
            (np.asarray(lat, dtype=np.float64) - self.lat0) * my,
        )

    def to_lonlat(self, x: ArrayLike, y: ArrayLike) -> tuple[FloatArray, FloatArray]:
        mx, my = self.metres_per_degree
        return (
            np.asarray(x, dtype=np.float64) / mx + self.lon0,
            np.asarray(y, dtype=np.float64) / my + self.lat0,
        )


@dataclass(frozen=True)
class Grid:
    """A north-up raster in the local frame. Row 0 is the northern edge."""

    x_min: float
    y_max: float
    res: float
    width: int
    height: int

    @property
    def x_max(self) -> float:
        return self.x_min + self.width * self.res

    @property
    def y_min(self) -> float:
        return self.y_max - self.height * self.res

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)

    def rowcol(self, x: ArrayLike, y: ArrayLike) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
        """Pixel indices for points. Indices can fall outside the grid; callers clip or mask."""
        col = np.floor((np.asarray(x, dtype=np.float64) - self.x_min) / self.res).astype(np.int64)
        row = np.floor((self.y_max - np.asarray(y, dtype=np.float64)) / self.res).astype(np.int64)
        return row, col

    def inside(self, row: NDArray[np.int64], col: NDArray[np.int64]) -> NDArray[np.bool_]:
        return (row >= 0) & (row < self.height) & (col >= 0) & (col < self.width)

    def centres(self) -> tuple[FloatArray, FloatArray]:
        """1-D arrays of pixel-centre x (per column) and y (per row)."""
        xs: FloatArray = self.x_min + (np.arange(self.width, dtype=np.float64) + 0.5) * self.res
        ys: FloatArray = self.y_max - (np.arange(self.height, dtype=np.float64) + 0.5) * self.res
        return xs, ys

    def to_dict(self) -> dict[str, float | int]:
        return {
            "x_min": self.x_min,
            "y_max": self.y_max,
            "res": self.res,
            "width": self.width,
            "height": self.height,
        }

    @staticmethod
    def from_dict(d: dict[str, float | int]) -> Grid:
        return Grid(
            x_min=float(d["x_min"]),
            y_max=float(d["y_max"]),
            res=float(d["res"]),
            width=int(d["width"]),
            height=int(d["height"]),
        )


def polyline_length(xs: FloatArray, ys: FloatArray) -> float:
    return float(np.hypot(np.diff(xs), np.diff(ys)).sum())


def sample_polyline(xs: FloatArray, ys: FloatArray, spacing: float) -> tuple[FloatArray, FloatArray]:
    """Points at the midpoints of equal intervals no longer than `spacing` along a polyline.

    Midpoints rather than endpoints so that every sample stands for the same
    length of path and nothing is double counted where two segments meet.
    """
    seg = np.hypot(np.diff(xs), np.diff(ys))
    total = float(seg.sum())
    if total <= 0:
        return xs[:1].copy(), ys[:1].copy()
    n = max(1, int(math.ceil(total / spacing)))
    at = (np.arange(n) + 0.5) * (total / n)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    return np.interp(at, cum, xs), np.interp(at, cum, ys)
