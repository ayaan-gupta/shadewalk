"""Milestone 3: canopy shadows, the shade-weighted router, the slider and the heat factor."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from shadewalk.routing import BASE_DETOUR_CAP, DEFAULT_WEIGHT, MAX_WEIGHT, detour_cap, edge_costs, heat_factor, plan
from shadewalk.store import Dataset
from shadewalk.weather import ClimatologyWeather, OpenMeteoWeather
from validation.acceptance import sample_pairs

FIXTURE = Path(__file__).parent / "fixtures" / "open_meteo_forecast.json"
TZ = ZoneInfo("America/Chicago")


def test_cost_is_the_prd_formula() -> None:
    lengths = np.array([100.0, 100.0, 50.0])
    shade = np.array([1.0, 0.0, 0.5], dtype=np.float32)
    # cost = length * (1 + w * (1 - shade) * heat_factor)
    assert edge_costs(lengths, shade, 2.0, 0.5) == pytest.approx([100.0, 200.0, 75.0])
    assert edge_costs(lengths, shade, 0.0, 1.0) == pytest.approx(lengths.tolist())


def test_heat_factor_scales_with_temperature() -> None:
    assert heat_factor(10) == 0 and heat_factor(20) == 0
    assert heat_factor(27.5) == pytest.approx(0.5)
    assert heat_factor(35) == pytest.approx(1.0)
    assert heat_factor(50) == 1.5
    assert [heat_factor(t) for t in range(15, 46, 5)] == sorted(heat_factor(t) for t in range(15, 46, 5))


def test_detour_cap_only_relaxes_past_the_default_slider() -> None:
    assert detour_cap(0) == detour_cap(DEFAULT_WEIGHT) == BASE_DETOUR_CAP == 1.5
    assert detour_cap(DEFAULT_WEIGHT + 0.01) > 1.5
    assert detour_cap(MAX_WEIGHT) == 3.0


def test_canopy_only_ever_adds_shade(data: Dataset) -> None:
    table = data.shade
    assert (table.segments_all >= table.segments_buildings).all()
    lengths = data.network.lengths
    with_trees = float((table.segments(7, 900, "all") * lengths).sum() / lengths.sum())
    without = float((table.segments(7, 900, "buildings") * lengths).sum() / lengths.sum())
    assert with_trees - without > 0.03, "tree canopy should add several points of shade network-wide in July"
    assert (data.canopy_height > 0).mean() > 0.02 and float(data.canopy_height.max()) <= 30
    assert not ((data.canopy_height > 0) & (data.building_height > 0)).any()


def test_shadiest_route_trades_distance_for_shade(data: Dataset) -> None:
    shade = data.shade.segments(7, 900)
    improved = 0
    for a, b in sample_pairs(data.network, 60, seed=3):
        pair = plan(data.network, shade, a, b, DEFAULT_WEIGHT, 1.0)
        assert pair is not None
        assert pair.shadiest.distance_m >= pair.shortest.distance_m - 1e-6
        assert pair.shadiest.shade_share >= pair.shortest.shade_share - 1e-9
        improved += pair.shadiest.shade_share > pair.shortest.shade_share + 0.05
        off = plan(data.network, shade, a, b, 0.0, 1.0)
        assert off is not None and off.shadiest.edges == off.shortest.edges
        cool = plan(data.network, shade, a, b, DEFAULT_WEIGHT, heat_factor(15))
        assert cool is not None and cool.shadiest.edges == cool.shortest.edges
    assert improved >= 30


def test_detour_never_exceeds_the_cap_at_or_below_the_default_slider(data: Dataset) -> None:
    """PRD acceptance test 2, on 100 pairs, at the hottest heat factor and three times of day."""
    pairs = sample_pairs(data.network, 100, seed=11)
    binding = 0
    for month, minute in ((7, 900), (7, 540), (1, 600)):
        shade = data.shade.segments(month, minute)
        for a, b in pairs:
            for weight in (1.0, DEFAULT_WEIGHT):
                pair = plan(data.network, shade, a, b, weight, 1.5)
                assert pair is not None and pair.detour_ratio <= 1.5 + 1e-6
                binding += pair.capped
    assert binding > 0, "the cap should bind for some pair, or this test proves nothing"


def test_raising_the_slider_allows_longer_detours_up_to_its_own_cap(data: Dataset) -> None:
    shade = data.shade.segments(1, 600)
    longest = 0.0
    for a, b in sample_pairs(data.network, 100, seed=11):
        pair = plan(data.network, shade, a, b, MAX_WEIGHT, 1.5)
        assert pair is not None and pair.detour_ratio <= 3.0 + 1e-6
        longest = max(longest, pair.detour_ratio)
    assert longest > 1.5


def test_route_endpoint_reports_both_routes_and_the_conditions(client: TestClient) -> None:
    body = {"origin": {"lon": -96.8016, "lat": 32.7893}, "destination": {"lon": -96.7950, "lat": 32.7812}, "depart_at": "2026-07-15T15:00"}
    out = client.post("/api/route", json=body).json()
    assert out["conditions"]["temperature_source"] == "climatology"
    assert 30 < out["conditions"]["temperature_c"] < 38 and 0.7 < out["conditions"]["heat_factor"] < 1.2
    assert out["shadiest"]["shade_pct"] > out["shortest"]["shade_pct"]
    cmp = out["comparison"]
    assert cmp["extra_min"] == pytest.approx(out["shadiest"]["duration_min"] - out["shortest"]["duration_min"], abs=0.11)
    assert cmp["detour_ratio"] <= 1.5 and not cmp["same_route"]
    without_trees = client.post("/api/route", json={**body, "layer": "buildings"}).json()
    assert without_trees["shortest"]["shade_pct"] <= out["shortest"]["shade_pct"]
    night = client.post("/api/route", json={**body, "depart_at": "2026-07-15T23:00"}).json()
    assert night["comparison"]["same_route"] and not night["conditions"]["sun"]["up"]
    assert client.post("/api/route", json={**body, "shade_weight": 9}).status_code == 422


def test_offline_weather_is_a_month_by_hour_climatology(settings) -> None:  # type: ignore[no-untyped-def]
    climate = ClimatologyWeather.from_file(settings.data_dir / "climatology.json")
    july = climate.temperature(32.78, -96.8, datetime(2026, 7, 15, 15, 0, tzinfo=TZ))
    january = climate.temperature(32.78, -96.8, datetime(2026, 1, 15, 7, 0, tzinfo=TZ))
    assert july.source == "climatology" and 31 < july.temp_c < 38
    assert -2 < january.temp_c < 10
    half = climate.temperature(32.78, -96.8, datetime(2026, 7, 15, 15, 30, tzinfo=TZ))
    four = climate.temperature(32.78, -96.8, datetime(2026, 7, 15, 16, 0, tzinfo=TZ))
    assert half.temp_c == pytest.approx((july.temp_c + four.temp_c) / 2, abs=0.06)


def test_open_meteo_provider_against_a_recorded_response(settings) -> None:  # type: ignore[no-untyped-def]
    recorded = json.loads(FIXTURE.read_text())
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=recorded)

    climate = ClimatologyWeather.from_file(settings.data_dir / "climatology.json")
    provider = OpenMeteoWeather(fallback=climate, client=httpx.Client(transport=httpx.MockTransport(handler)))
    first = datetime.fromisoformat(recorded["hourly"]["time"][15]).replace(tzinfo=TZ)
    reading = provider.temperature(32.78, -96.8, first)
    assert reading.source == "forecast" and reading.temp_c == recorded["hourly"]["temperature_2m"][15]
    assert calls[0].url.params["hourly"] == "temperature_2m" and calls[0].url.params["timezone"] == "America/Chicago"
    provider.temperature(32.78, -96.8, first)
    assert len(calls) == 1, "the forecast is cached between requests"
    # July is months past the recorded forecast window, so the provider answers from the climatology.
    assert provider.temperature(32.78, -96.8, datetime(2027, 7, 15, 15, tzinfo=TZ)).source == "climatology"


def test_open_meteo_failure_falls_back_instead_of_failing_the_route(settings) -> None:  # type: ignore[no-untyped-def]
    climate = ClimatologyWeather.from_file(settings.data_dir / "climatology.json")
    down = OpenMeteoWeather(fallback=climate, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))))
    assert down.temperature(32.78, -96.8, datetime(2026, 10, 13, 15, tzinfo=TZ)).source == "climatology"
