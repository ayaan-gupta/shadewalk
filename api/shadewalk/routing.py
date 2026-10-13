"""Shortest and shadiest walking routes.

The PRD's cost for a segment at time t is

    cost = length * (1 + w * (1 - shade_fraction(t)) * heat_factor)

A fully shaded metre costs one metre. A fully sunny one costs 1 + w * heat_factor
metres. Because cost never drops below length, straight-line distance to the
goal is an admissible A* heuristic for any w.

The detour rule ("never more than 1.5 times the shortest distance unless the
user raises the slider") is a constraint, not a property of the cost, so it is
enforced separately: if the best route for the requested w is too long, w is
bisected down to the largest value whose route fits. Route length only grows
with w, which is what makes the bisection valid.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from numpy.typing import NDArray

from .network import Network

# Slider semantics. Up to DEFAULT_WEIGHT the detour cap is the PRD's 1.5.
# Past it the user has "raised the slider" and the cap relaxes linearly.
DEFAULT_WEIGHT = 2.0
MAX_WEIGHT = 5.0
BASE_DETOUR_CAP = 1.5
MAX_DETOUR_CAP = 3.0
BISECTION_STEPS = 10


def detour_cap(weight: float) -> float:
    """How many times the shortest distance the shadiest route may be, for a slider value."""
    if weight <= DEFAULT_WEIGHT:
        return BASE_DETOUR_CAP
    t = min((weight - DEFAULT_WEIGHT) / (MAX_WEIGHT - DEFAULT_WEIGHT), 1.0)
    return BASE_DETOUR_CAP + t * (MAX_DETOUR_CAP - BASE_DETOUR_CAP)


def heat_factor(temp_c: float) -> float:
    """How much shade matters at a forecast air temperature.

    Zero at 20 C and below, where sun on a walk is welcome. One at 35 C, a
    normal July afternoon in Dallas. Keeps rising to 1.5 at 42.5 C.
    """
    return float(min(max((temp_c - 20.0) / 15.0, 0.0), 1.5))


def edge_costs(lengths: NDArray[np.float64], shade: NDArray[np.floating], weight: float, heat: float) -> list[float]:
    """The PRD cost for every edge, as a plain list because the A* loop indexes it a lot."""
    costs: list[float] = (lengths * (1.0 + weight * (1.0 - shade.astype(np.float64)) * heat)).tolist()
    return costs


def astar(net: Network, source: int, target: int, cost: Sequence[float]) -> list[int] | None:
    """Edge ids of the cheapest path from source to target, or None if there is none."""
    if source == target:
        return []
    xs, ys = net.node_x.tolist(), net.node_y.tolist()
    tx, ty = xs[target], ys[target]
    best: dict[int, float] = {source: 0.0}
    came: dict[int, tuple[int, int]] = {}
    heap: list[tuple[float, float, int]] = [(math.hypot(xs[source] - tx, ys[source] - ty), 0.0, source)]
    adjacency = net.adjacency
    while heap:
        _, g, node = heapq.heappop(heap)
        if node == target:
            path: list[int] = []
            while node != source:
                node, edge = came[node]
                path.append(edge)
            path.reverse()
            return path
        if g > best.get(node, math.inf):
            continue
        for neighbour, edge in adjacency[node]:
            candidate = g + cost[edge]
            if candidate < best.get(neighbour, math.inf):
                best[neighbour] = candidate
                came[neighbour] = (node, edge)
                heapq.heappush(heap, (candidate + math.hypot(xs[neighbour] - tx, ys[neighbour] - ty), candidate, neighbour))
    return None


@dataclass(frozen=True)
class RouteStats:
    edges: list[int]
    distance_m: float
    shaded_m: float

    @property
    def shade_share(self) -> float:
        return self.shaded_m / self.distance_m if self.distance_m > 0 else 0.0


@dataclass(frozen=True)
class RoutePair:
    shortest: RouteStats
    shadiest: RouteStats
    weight_requested: float
    weight_used: float
    cap: float
    capped: bool

    @property
    def detour_ratio(self) -> float:
        return self.shadiest.distance_m / self.shortest.distance_m if self.shortest.distance_m > 0 else 1.0


def measure(net: Network, edges: list[int], shade: NDArray[np.floating]) -> RouteStats:
    ids = np.array(edges, dtype=np.int64)
    lengths = net.lengths[ids]
    return RouteStats(edges=edges, distance_m=float(lengths.sum()), shaded_m=float((lengths * shade[ids]).sum()))


def plan(
    net: Network,
    shade: NDArray[np.floating],
    source: int,
    target: int,
    weight: float = DEFAULT_WEIGHT,
    heat: float = 1.0,
    cap: float | None = None,
) -> RoutePair | None:
    """Both routes for one origin, destination and moment. None when the two nodes are not connected."""
    weight = min(max(weight, 0.0), MAX_WEIGHT)
    limit = detour_cap(weight) if cap is None else cap
    shortest_edges = astar(net, source, target, net.lengths.tolist())
    if shortest_edges is None:
        return None
    shortest = measure(net, shortest_edges, shade)
    allowed = shortest.distance_m * limit + 1e-6

    def route_for(w: float) -> RouteStats:
        edges = astar(net, source, target, edge_costs(net.lengths, shade, w, heat))
        assert edges is not None  # connected, or the shortest search would have failed
        return measure(net, edges, shade)

    if weight * heat <= 0:
        return RoutePair(shortest, shortest, weight, 0.0, limit, False)
    best = route_for(weight)
    used, capped = weight, False
    if best.distance_m > allowed:
        capped = True
        low, high = 0.0, weight
        best, used = shortest, 0.0
        for _ in range(BISECTION_STEPS):
            mid = (low + high) / 2
            candidate = route_for(mid)
            if candidate.distance_m <= allowed:
                low = mid
                if candidate.shaded_m / candidate.distance_m >= best.shaded_m / max(best.distance_m, 1e-9):
                    best, used = candidate, mid
            else:
                high = mid
    # Never hand back a "shadiest" route that is sunnier than the shortest one.
    if best.shade_share < shortest.shade_share:
        best, used = shortest, 0.0
    return RoutePair(shortest, best, weight, used, limit, capped)
