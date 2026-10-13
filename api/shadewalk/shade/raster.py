"""Shadow casting on a height raster.

The model: every cell of the raster is a column of the given height standing on
flat ground (buildings as prisms, tree canopy as a solid block up to its top).
A ground point is in shadow when some column toward the sun is tall enough to
block the ray: there is a distance d > 0 with

    height(p + d * s) - receiver > d * tan(elevation)

where s is the horizontal unit vector pointing at the sun.

Checking that by marching rays costs O(cells * shadow length). Instead the
raster is resampled into a frame whose columns run along s. Along one row of
that frame the condition for cell i is

    max over j > i of (H[j] - j*k)  >  receiver - i*k,     k = res * tan(elevation)

and the left side is a suffix maximum, which numpy computes for every row at
once. One sun position over the 4.6 million cell pilot grid takes about a
quarter of a second, independent of how long the shadows are.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from ..geo import FloatArray, Grid

BoolArray = NDArray[np.bool_]


@dataclass(frozen=True)
class SunFrame:
    """The rotated frame for one sun azimuth: u runs toward the sun, v is perpendicular."""

    grid: Grid
    azimuth_deg: float
    size: int

    @property
    def _axes(self) -> tuple[float, float, float, float]:
        az = math.radians(self.azimuth_deg)
        # s = unit vector toward the sun (east, north); n = s rotated 90 degrees clockwise.
        sx, sy = math.sin(az), math.cos(az)
        return sx, sy, sy, -sx

    @property
    def _centre(self) -> tuple[float, float]:
        g = self.grid
        return (g.x_min + g.x_max) / 2, (g.y_min + g.y_max) / 2

    def world_of_cells(self) -> tuple[FloatArray, FloatArray]:
        """World x, y of every cell centre in the rotated frame, as (size, size) arrays."""
        sx, sy, nx, ny = self._axes
        cx, cy = self._centre
        t = (np.arange(self.size, dtype=np.float32) - (self.size - 1) / 2) * np.float32(self.grid.res)
        u, v = t[None, :], t[:, None]
        return cx + u * sx + v * nx, cy + u * sy + v * ny

    def cells_of_world(self, x: NDArray[np.floating], y: NDArray[np.floating]) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
        """Rotated-frame (row, col) of world points. Always inside the frame for points on the grid."""
        sx, sy, nx, ny = self._axes
        cx, cy = self._centre
        dx, dy = np.asarray(x) - cx, np.asarray(y) - cy
        half = (self.size - 1) / 2
        col = np.rint((dx * sx + dy * sy) / self.grid.res + half).astype(np.int64)
        row = np.rint((dx * nx + dy * ny) / self.grid.res + half).astype(np.int64)
        return np.clip(row, 0, self.size - 1), np.clip(col, 0, self.size - 1)


@dataclass(frozen=True)
class Shadow:
    """The result of one cast, still in the rotated frame."""

    frame: SunFrame
    mask: BoolArray

    def at(self, x: NDArray[np.floating], y: NDArray[np.floating]) -> BoolArray:
        """Whether each world point is in shadow."""
        row, col = self.frame.cells_of_world(x, y)
        out: BoolArray = self.mask[row, col]
        return out

    def to_grid(self) -> BoolArray:
        """The shadow mask resampled back onto the north-up grid."""
        xs, ys = self.frame.grid.centres()
        gx, gy = np.meshgrid(xs.astype(np.float32), ys.astype(np.float32))
        return self.at(gx, gy)


def cast_shadow(
    height: NDArray[np.floating],
    grid: Grid,
    sun_azimuth_deg: float,
    sun_elevation_deg: float,
    receiver_height: float = 0.0,
) -> Shadow:
    """Cast shadows of a height raster for one sun position.

    `height` is metres above ground, zero where there is nothing. The returned
    mask marks ground cells shadowed by some *other* cell toward the sun. A
    cell that is itself under a roof or a crown is not marked unless something
    else also shades it, so callers decide what standing under an obstacle means.
    """
    if height.shape != grid.shape:
        raise ValueError(f"height is {height.shape}, grid is {grid.shape}")
    size = int(math.ceil(math.hypot(grid.width, grid.height))) + 2
    frame = SunFrame(grid=grid, azimuth_deg=sun_azimuth_deg, size=size)
    if sun_elevation_deg <= 0:
        return Shadow(frame=frame, mask=np.ones((size, size), dtype=bool))

    wx, wy = frame.world_of_cells()
    row, col = grid.rowcol(wx, wy)
    ok = grid.inside(row, col)
    rotated = np.zeros((size, size), dtype=np.float32)
    rotated[ok] = height[row[ok], col[ok]]

    k = np.float32(grid.res * math.tan(math.radians(sun_elevation_deg)))
    ramp = np.arange(size, dtype=np.float32) * k
    lifted = rotated - ramp[None, :]
    # Suffix maximum over strictly greater column indices (strictly toward the sun).
    toward_sun = np.maximum.accumulate(lifted[:, ::-1], axis=1)[:, ::-1]
    blocker = np.full((size, size), -np.inf, dtype=np.float32)
    blocker[:, :-1] = toward_sun[:, 1:]
    # A column fills its whole cell, so its sunward neighbour's wall is half a cell
    # closer than its centre. Without the half step every shadow comes up 0.5 m short.
    mask: BoolArray = blocker > (np.float32(receiver_height) - ramp[None, :] - np.float32(0.5) * k)
    return Shadow(frame=frame, mask=mask)


def shade_fraction(covered: BoolArray, counts: NDArray[np.int64]) -> FloatArray:
    """Mean of a boolean per-sample array within consecutive groups of the given sizes."""
    ends = np.cumsum(counts)
    starts = ends - counts
    running = np.concatenate([[0], np.cumsum(covered, dtype=np.int64)])
    out: FloatArray = (running[ends] - running[starts]) / np.maximum(counts, 1)
    return out
