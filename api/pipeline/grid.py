"""The pilot's local frame and raster grid, derived from the pilot bbox."""

from __future__ import annotations

import math

import numpy as np

from shadewalk.geo import Grid, LocalFrame

from .config import PILOT


def pilot_frame() -> LocalFrame:
    lat0, lon0 = PILOT.centre
    return LocalFrame(lat0=lat0, lon0=lon0)


def pilot_extent_xy() -> tuple[float, float, float, float]:
    """The walking area in local metres: x_min, y_min, x_max, y_max."""
    w, s, e, n = PILOT.bbox
    xs, ys = pilot_frame().to_xy(np.array([w, e]), np.array([s, n]))
    return (float(xs[0]), float(ys[0]), float(xs[1]), float(ys[1]))


def pilot_grid() -> Grid:
    """The walking area plus the shadow-caster buffer, snapped out to whole cells."""
    x0, y0, x1, y1 = pilot_extent_xy()
    res, b = PILOT.grid_res_m, PILOT.buffer_m
    x_min = math.floor((x0 - b) / res) * res
    y_max = math.ceil((y1 + b) / res) * res
    width = int(math.ceil((x1 + b - x_min) / res))
    height = int(math.ceil((y_max - (y0 - b)) / res))
    return Grid(x_min=x_min, y_max=y_max, res=res, width=width, height=height)
