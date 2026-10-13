"""Milestone 1: the walking graph, shortest paths and the route endpoint."""

from __future__ import annotations

import heapq
import random

import pytest
from fastapi.testclient import TestClient

from shadewalk.geo import LocalFrame, polyline_length, sample_polyline
from shadewalk.network import Network
from shadewalk.routing import astar
from shadewalk.store import Dataset

KLYDE_WARREN = {"lon": -96.8016, "lat": 32.7893}
MAIN_STREET_GARDEN = {"lon": -96.7950, "lat": 32.7812}


def dijkstra(net: Network, source: int, target: int) -> float:
    best = {source: 0.0}
    heap = [(0.0, source)]
    while heap:
        d, node = heapq.heappop(heap)
        if node == target:
            return d
        if d > best[node]:
            continue
        for neighbour, edge in net.adjacency[node]:
            nd = d + net.edges[edge].length_m
            if nd < best.get(neighbour, float("inf")):
                best[neighbour] = nd
                heapq.heappush(heap, (nd, neighbour))
    raise AssertionError("not connected")


def test_local_frame_round_trips_and_measures_a_known_distance() -> None:
    frame = LocalFrame(lat0=32.7835, lon0=-96.79975)
    x, y = frame.to_xy(-96.7935, 32.7905)
    lon, lat = frame.to_lonlat(x, y)
    assert abs(float(lon) + 96.7935) < 1e-9 and abs(float(lat) - 32.7905) < 1e-9
    # One arc second of latitude is 30.8 m at this latitude.
    _, north = frame.to_xy(-96.79975, 32.7835 + 1 / 3600)
    assert abs(float(north) - 30.81) < 0.05


def test_polyline_samples_stand_for_equal_lengths() -> None:
    import numpy as np

    xs, ys = np.array([0.0, 10.0, 10.0]), np.array([0.0, 0.0, 5.0])
    sx, sy = sample_polyline(xs, ys, 1.0)
    assert len(sx) == 15 and polyline_length(xs, ys) == 15
    assert sx[0] == pytest.approx(0.5) and sy[-1] == pytest.approx(4.5)


def test_graph_is_one_connected_outdoor_network(data: Dataset) -> None:
    net = data.network
    assert net.node_count > 2000 and net.edge_count > 3000
    seen, stack = {0}, [0]
    while stack:
        for neighbour, _ in net.adjacency[stack.pop()]:
            if neighbour not in seen:
                seen.add(neighbour)
                stack.append(neighbour)
    assert len(seen) == net.node_count
    assert all(e.length_m > 0 and len(e.coords) >= 2 for e in net.edges)
    w, s, e, n = data.bbox
    inside = ((net.node_lon > w - 0.004) & (net.node_lon < e + 0.004) & (net.node_lat > s - 0.004) & (net.node_lat < n + 0.004)).mean()
    assert inside == 1.0


def test_astar_matches_dijkstra_on_random_pairs(data: Dataset) -> None:
    net = data.network
    rng = random.Random(1)
    lengths = net.lengths.tolist()
    for _ in range(40):
        a, b = rng.randrange(net.node_count), rng.randrange(net.node_count)
        path = astar(net, a, b, lengths)
        assert path is not None
        assert sum(lengths[e] for e in path) == pytest.approx(dijkstra(net, a, b), abs=1e-6)


def test_route_endpoint_returns_a_connected_walk(client: TestClient) -> None:
    body = {"origin": KLYDE_WARREN, "destination": MAIN_STREET_GARDEN, "depart_at": "2026-07-15T15:00", "shade_weight": 0}
    out = client.post("/api/route", json=body).json()
    route = out["shortest"]
    assert 1000 < route["distance_m"] < 1600
    assert route["distance_m"] == pytest.approx(sum(leg["length_m"] for leg in route["legs"]), abs=0.5)
    assert route["legs"][0]["coords"][0] == [out["origin"]["lon"], out["origin"]["lat"]]
    assert route["legs"][-1]["coords"][-1] == [out["destination"]["lon"], out["destination"]["lat"]]
    for before, after in zip(route["legs"], route["legs"][1:]):
        assert before["coords"][-1] == after["coords"][0]
    assert route["duration_min"] == pytest.approx(route["distance_m"] / 1.3 / 60, abs=0.06)


def test_points_outside_the_pilot_are_refused(client: TestClient) -> None:
    body = {"origin": {"lon": -96.90, "lat": 32.70}, "destination": MAIN_STREET_GARDEN, "depart_at": "2026-07-15T15:00"}
    response = client.post("/api/route", json=body)
    assert response.status_code == 422 and "pilot" in response.json()["detail"]
    same = client.post("/api/route", json={"origin": KLYDE_WARREN, "destination": KLYDE_WARREN, "depart_at": "2026-07-15T15:00"})
    assert same.status_code == 422


def test_static_layers_are_served(client: TestClient) -> None:
    network = client.get("/api/network").json()
    assert network["features"][5]["id"] == 5 and network["features"][5]["geometry"]["type"] == "LineString"
    meta = client.get("/api/meta").json()
    assert meta["counts"]["segments"] == len(network["features"])
    assert meta["slider"] == {"min": 0.0, "max": 5.0, "default": 2.0, "base_cap": 1.5, "max_cap": 3.0}
    assert client.get("/api/health").json()["store"] == "files"
