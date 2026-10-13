"""Milestone 2: sun position, shadow casting and the per-segment shade table."""

from __future__ import annotations

import math
import zlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from fastapi.testclient import TestClient

from shadewalk.geo import Grid, sample_polyline
from shadewalk.shade.raster import cast_shadow, shade_fraction
from shadewalk.shade.table import SCALE
from shadewalk.store import Dataset


def box_world(res: float = 1.0) -> tuple[Grid, np.ndarray]:
    """One box, 20 m east-west by 10 m north-south and 10 m tall, centred on the origin."""
    n = int(200 / res)
    grid = Grid(x_min=-100, y_max=100, res=res, width=n, height=n)
    xs, ys = grid.centres()
    gx, gy = np.meshgrid(xs, ys)
    height = np.zeros(grid.shape, dtype=np.float32)
    height[(np.abs(gx) < 10) & (np.abs(gy) < 5)] = 10
    return grid, height


@pytest.mark.parametrize("azimuth,elevation", [(180, 45), (225, 45), (90, 30), (247, 62), (300, 20), (135, 70)])
def test_shadow_area_of_a_box_matches_the_closed_form(azimuth: float, elevation: float) -> None:
    grid, height = box_world()
    ground = cast_shadow(height, grid, azimuth, elevation).to_grid() & (height == 0)
    reach = 10 / math.tan(math.radians(elevation))
    dx, dy = reach * math.sin(math.radians(azimuth)), reach * math.cos(math.radians(azimuth))
    # A w by d rectangle swept along (dx, dy) uncovers |dx|*d + |dy|*w of new ground.
    expected = abs(dx) * 10 + abs(dy) * 20
    assert float(ground.sum()) == pytest.approx(expected, rel=0.08, abs=12)


def test_a_street_north_of_the_box_is_half_shaded_at_noon() -> None:
    """Sun due south at 45 degrees: the shadow is 10 m deep and as wide as the box.

    A 40 m east-west street 5 m north of the wall has exactly its middle 20 m in shade.
    """
    grid, height = box_world()
    xs, ys = sample_polyline(np.array([-20.0, 20.0]), np.array([10.0, 10.0]), 1.0)
    shadow = cast_shadow(height, grid, 180, 45)
    assert float(shadow.at(xs, ys).mean()) == pytest.approx(0.5, abs=0.05)
    # Move the street beyond the shadow's 10 m reach and it is in full sun.
    far = cast_shadow(height, grid, 180, 45).at(xs, ys + 7.0)
    assert not far.any()
    # Lower the sun to 26.57 degrees (tan = 0.5) and the shadow doubles to 20 m.
    low = cast_shadow(height, grid, 180, math.degrees(math.atan(0.5))).at(xs, ys + 7.0)
    assert float(low.mean()) == pytest.approx(0.5, abs=0.05)


def test_no_shadow_falls_on_the_sunward_side_and_night_is_all_shade() -> None:
    grid, height = box_world()
    south = cast_shadow(height, grid, 180, 30).to_grid()
    _, ys = grid.centres()
    assert not south[ys < -6].any()
    assert cast_shadow(height, grid, 180, -5).to_grid().all()


def test_shade_fraction_groups_samples_by_segment() -> None:
    covered = np.array([1, 1, 0, 0, 1, 0, 0, 0, 0], dtype=bool)
    assert shade_fraction(covered, np.array([4, 1, 4])).tolist() == [0.5, 1.0, 0.0]


def test_stored_sun_table_is_pvlib_for_the_representative_day(data: Dataset) -> None:
    from pvlib import solarposition
    import pandas as pd

    w, s, e, n = data.bbox
    tz = ZoneInfo(data.meta["timezone"])
    for month, hour, minute in [(1, 9, 0), (7, 15, 0), (7, 15, 45), (10, 12, 30), (12, 16, 15)]:
        when = datetime(2025, month, 15, tzinfo=tz) + timedelta(hours=hour, minutes=minute)
        truth = solarposition.get_solarposition(pd.DatetimeIndex([when]), (s + n) / 2, (w + e) / 2)
        sun = data.shade.sun(month, hour * 60 + minute)
        assert sun.azimuth_deg == pytest.approx(float(truth["azimuth"].iloc[0]), abs=0.02)
        assert sun.elevation_deg == pytest.approx(float(truth["apparent_elevation"].iloc[0]), abs=0.02)
    # July at 3 PM daylight time is still early afternoon by the sun: high, in the west-southwest.
    july = data.shade.sun(7, 900)
    assert 60 < july.elevation_deg < 72 and 235 < july.azimuth_deg < 255


def test_shade_table_shape_night_and_noon(data: Dataset) -> None:
    table = data.shade
    assert table.segments_all.shape == (12, 24, data.network.edge_count)
    assert int(table.segments_all.max()) <= SCALE
    assert (table.segments_all[6, 2] == SCALE).all(), "3 AM is all shade"
    lengths = data.network.lengths
    noon = float((table.segments(7, 13 * 60) * lengths).sum() / lengths.sum())
    evening = float((table.segments(7, 19 * 60) * lengths).sum() / lengths.sum())
    assert 0.05 < noon < 0.5 < evening, (noon, evening)
    # Between two table rows the lookup blends linearly.
    a, b, mid = table.segments(7, 900), table.segments(7, 960), table.segments(7, 930)
    assert np.allclose(mid, (a + b) / 2, atol=1e-6)


def test_tall_buildings_shade_more_than_the_default_height_would(data: Dataset) -> None:
    """Doubling every building must not reduce any segment's shade. Guards the direction of the cast."""
    rows, cols = slice(900, 1300), slice(700, 1100)
    grid = Grid(x_min=0, y_max=400, res=1.0, width=400, height=400)
    height = data.building_height[rows, cols]
    sun = data.shade.sun(7, 900)
    low = cast_shadow(height, grid, sun.azimuth_deg, sun.elevation_deg).to_grid()
    high = cast_shadow(height * 2, grid, sun.azimuth_deg, sun.elevation_deg).to_grid()
    assert height.max() > 30 and low.sum() > 0
    assert high.sum() > low.sum() and not (low & ~high).any()


def test_shadow_overlay_is_a_valid_png_of_the_walking_area(client: TestClient, data: Dataset) -> None:
    png = client.get("/api/shadow.png", params={"month": 7, "minute": 900}).content
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    mx, my = data.frame.metres_per_degree
    w, s, e, n = data.bbox
    assert width == pytest.approx((e - w) * mx, abs=2) and height == pytest.approx((n - s) * my, abs=2)
    at = png.index(b"IDAT")
    size = int.from_bytes(png[at - 4 : at], "big")
    raw = zlib.decompress(png[at + 4 : at + 4 + size])
    pixels = np.frombuffer(raw, dtype=np.uint8).reshape(height, width + 1)[:, 1:]
    assert set(np.unique(pixels).tolist()) == {0, 1, 2}
    assert 0.1 < float((pixels > 0).mean()) < 0.6
    meta = client.get("/api/meta").json()
    assert meta["overlay"]["corners"][0] == pytest.approx([w, n], abs=2e-5)
    night = client.get("/api/shadow.png", params={"month": 7, "minute": 120}).content
    assert len(night) < 5000
