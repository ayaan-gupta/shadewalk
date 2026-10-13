"""Milestone 4: the time slider's data, the planner view and the validation checks."""

from __future__ import annotations

import ast
import os
from datetime import UTC
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from shadewalk.routing import DEFAULT_WEIGHT
from shadewalk.store import Dataset, DemandRadii
from shadewalk.store.files import count_demand, point_to_polyline_m
from validation import acceptance, independent


def test_shade_layer_changes_through_the_day(client: TestClient) -> None:
    by_minute = {m: client.get("/api/shade", params={"month": 7, "minute": m}).json() for m in (540, 780, 900, 1140)}
    assert len(by_minute[900]["shade_pct"]) == client.get("/api/meta").json()["counts"]["segments"]
    assert all(0 <= v <= 100 for v in by_minute[900]["shade_pct"])
    assert by_minute[780]["network_shade_pct"] < by_minute[540]["network_shade_pct"]
    assert by_minute[780]["network_shade_pct"] < by_minute[1140]["network_shade_pct"]
    assert by_minute[540]["sun"]["azimuth_deg"] < 180 < by_minute[1140]["sun"]["azimuth_deg"]
    assert client.get("/api/shade", params={"month": 13, "minute": 0}).status_code == 422


def test_point_to_polyline_distance() -> None:
    xs, ys = np.array([0.0, 10.0, 10.0]), np.array([0.0, 0.0, 10.0])
    assert point_to_polyline_m(5, 3, xs, ys) == pytest.approx(3)
    assert point_to_polyline_m(13, 14, xs, ys) == pytest.approx(5)


def test_planner_ranks_sunny_blocks_near_stops_and_schools(client: TestClient, data: Dataset) -> None:
    out = client.get("/api/planner", params={"month": 7, "start_hour": 12, "end_hour": 18, "limit": 25}).json()
    blocks = out["blocks"]
    assert len(blocks) == 25
    assert [b["priority"] for b in blocks] == sorted((b["priority"] for b in blocks), reverse=True)
    for b in blocks:
        demand = b["bus_stops"] + 2 * b["rail_stops"] + 3 * b["schools"]
        assert demand > 0 and b["kind"] in ("sidewalk", "path", "street") and b["length_m"] >= 20
        assert b["priority"] == pytest.approx((1 - b["shade_pct"] / 100) * demand, abs=0.01)
    stops = out["stops"]
    assert len(stops) == out["stop_count"] == sum(p.kind in ("bus_stop", "rail_stop") for p in data.pois)
    assert [s["shade_pct"] for s in stops] == sorted(s["shade_pct"] for s in stops)
    assert out["unshaded_stops"] == sum(s["shade_pct"] < 10 for s in stops)
    assert client.get("/api/planner", params={"start_hour": 18, "end_hour": 12}).status_code == 422


def test_demand_counts_respect_their_radii(data: Dataset) -> None:
    near = count_demand(data.network, data.pois, DemandRadii())
    wide = count_demand(data.network, data.pois, DemandRadii(bus_stop=80, rail_stop=160, school=300))
    assert (wide.bus_stops >= near.bus_stops).all() and wide.bus_stops.sum() > near.bus_stops.sum()
    assert near.bus_stops.max() >= 1 and near.schools.max() >= 1
    none = count_demand(data.network, data.pois, DemandRadii(bus_stop=0, rail_stop=0, school=0))
    # A stop mapped as a node of the sidewalk itself is at distance zero, so a few survive.
    assert none.bus_stops.sum() < near.bus_stops.sum() / 4


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="needs PostGIS: set DATABASE_URL")
def test_postgis_store_agrees_with_the_files(settings, data: Dataset) -> None:  # type: ignore[no-untyped-def]
    from shadewalk.store.postgis import PostgisStore

    store = PostgisStore(os.environ["DATABASE_URL"], settings.data_dir)
    loaded = store.load()
    assert loaded.network.edge_count == data.network.edge_count
    assert np.allclose(loaded.network.lengths, data.network.lengths)
    assert loaded.network.edges[100].coords == data.network.edges[100].coords
    assert np.array_equal(loaded.shade.segments_all, data.shade.segments_all)
    assert np.array_equal(loaded.shade.pois_buildings, data.shade.pois_buildings)
    assert len(loaded.buildings["features"]) == len(data.buildings["features"])
    # The spatial join in SQL (ST_DWithin on geography) and the numpy twin must count the same things.
    sql, local = store.demand(DemandRadii()), count_demand(data.network, data.pois, DemandRadii())
    for a, b in ((sql.bus_stops, local.bus_stops), (sql.rail_stops, local.rail_stops), (sql.schools, local.schools)):
        assert (a != b).mean() < 0.002 and abs(int(a.sum()) - int(b.sum())) <= 3


def test_independent_check_shares_no_code_with_the_shade_model() -> None:
    tree = ast.parse(Path(independent.__file__).read_text())
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not any(name.startswith(("shadewalk", "pvlib", "pipeline")) for name in imported), imported


def test_independent_sun_position_matches_pvlib() -> None:
    from datetime import datetime

    import pandas as pd
    from pvlib import solarposition

    for stamp in ("2025-07-15T20:00", "2025-01-15T15:00", "2025-04-15T22:00", "2025-10-15T14:30"):
        when = datetime.fromisoformat(stamp).replace(tzinfo=UTC)
        truth = solarposition.get_solarposition(pd.DatetimeIndex([when]), 32.7835, -96.79975)
        azimuth, elevation = independent.noaa_sun(when, 32.7835, -96.79975)
        assert azimuth == pytest.approx(float(truth["azimuth"].iloc[0]), abs=0.1)
        assert elevation == pytest.approx(float(truth["apparent_elevation"].iloc[0]), abs=0.1)


def test_independent_check_on_a_single_box_at_a_known_sun_angle() -> None:
    """The analytic case again, through the other implementation: sun due south at 45 degrees."""
    box = np.array([[-10.0, -5.0], [10.0, -5.0], [10.0, 5.0], [-10.0, 5.0], [-10.0, -5.0]])
    world = independent.World(
        meta={"grid": {"x_min": -100, "y_max": 100, "res": 1.0, "width": 200, "height": 200}},
        edges=[],
        prisms=[([box], 10.0, -10.0, -5.0, 10.0, 5.0)],
        canopy=np.zeros((200, 200)),
    )
    street = {"covered": False, "xy": np.array([[-20.0, 10.0], [20.0, 10.0]])}
    assert independent.segment_shade(world, street, 180, 45) == pytest.approx(0.5, abs=0.01)
    assert independent.segment_shade(world, {**street, "xy": street["xy"] + [0, 6]}, 180, 45) == 0
    east = {"covered": False, "xy": np.array([[12.0, -15.0], [12.0, 15.0]])}
    # Sun due west at 45 degrees throws the shadow 10 m east: a north-south street 2 m east of the wall is shaded for 10 of its 30 m.
    assert independent.segment_shade(world, east, 270, 45) == pytest.approx(1 / 3, abs=0.01)
    world.canopy[85:95, 120:130] = 8.0  # a crown over x 20..30, y 5..15
    under = {"covered": False, "xy": np.array([[20.0, 10.0], [40.0, 10.0]])}
    assert independent.segment_shade(world, under, 180, 80) == pytest.approx(0.5, abs=0.02)


def test_acceptance_3_twenty_segments_agree_within_15_points() -> None:
    result = independent.run(7, 15)
    assert result["count"] == 20
    assert result["max_diff_points"] <= 15, result["segments"]
    values = [r["model_pct"] for r in result["segments"]]
    assert min(values) < 20 and max(values) > 60, "the sample must span sunny and shady segments"


def test_acceptance_1_shadiest_route_has_25_percent_more_shade_for_half_the_pairs(data: Dataset) -> None:
    pairs = acceptance.sample_pairs(data.network, 120)
    heat = 0.96  # July 3 PM climatology, 34.4 C
    for layer in ("all", "buildings"):
        result = acceptance.shade_gain(data.network, data.shade, pairs, layer, DEFAULT_WEIGHT, heat)  # type: ignore[arg-type]
        assert result["share"] >= 0.5, result
        assert result["max_detour_ratio"] <= 1.5 + 1e-6


def test_acceptance_4_route_responses_are_under_a_second(data: Dataset) -> None:
    timing = acceptance.latency(acceptance.sample_pairs(data.network, 100), data.network)
    assert timing["p95_ms"] < 1000 and timing["max_ms"] < 1000, timing
