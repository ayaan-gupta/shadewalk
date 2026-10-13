"""Request and response shapes for the HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .routing import DEFAULT_WEIGHT, MAX_WEIGHT


class LonLat(BaseModel):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)


class RouteRequest(BaseModel):
    origin: LonLat
    destination: LonLat
    # Pilot-local wall-clock time, e.g. "2026-07-15T15:00". Any offset is ignored.
    depart_at: datetime
    shade_weight: float = Field(default=DEFAULT_WEIGHT, ge=0, le=MAX_WEIGHT)
    layer: Literal["all", "buildings"] = "all"


class SnappedPoint(BaseModel):
    lon: float
    lat: float
    node: int
    snapped_m: float


class SunOut(BaseModel):
    azimuth_deg: float
    elevation_deg: float
    up: bool


class Conditions(BaseModel):
    depart_at: str
    month: int
    minute: int
    sun: SunOut
    temperature_c: float
    temperature_source: Literal["forecast", "climatology"]
    temperature_detail: str
    heat_factor: float


class Leg(BaseModel):
    segment_id: int
    shade: float
    length_m: float
    street: str | None
    coords: list[list[float]]


class RouteOut(BaseModel):
    distance_m: float
    duration_min: float
    shade_pct: float
    shaded_m: float
    sunny_m: float
    sun_min: float
    legs: list[Leg]


class Comparison(BaseModel):
    extra_m: float
    extra_min: float
    shade_gain_points: float
    sun_min_saved: float
    detour_ratio: float
    detour_cap: float
    capped: bool
    weight_requested: float
    weight_used: float
    same_route: bool


class RouteResponse(BaseModel):
    origin: SnappedPoint
    destination: SnappedPoint
    conditions: Conditions
    shortest: RouteOut
    shadiest: RouteOut
    comparison: Comparison
    elapsed_ms: float


class ShadeResponse(BaseModel):
    month: int
    minute: int
    layer: Literal["all", "buildings"]
    sun: SunOut
    network_shade_pct: float
    # One integer percentage per segment, indexed by segment id.
    shade_pct: list[int]


class BlockOut(BaseModel):
    segment_id: int
    street: str | None
    kind: str
    length_m: float
    shade_pct: float
    bus_stops: int
    rail_stops: int
    schools: int
    demand: float
    priority: float
    lon: float
    lat: float
    coords: list[list[float]]


class StopOut(BaseModel):
    id: int
    kind: str
    name: str | None
    lon: float
    lat: float
    shade_pct: float


class PlannerResponse(BaseModel):
    month: int
    start_hour: int
    end_hour: int
    layer: Literal["all", "buildings"]
    store: str
    network_shade_pct: float
    low_shade_km: float
    unshaded_stops: int
    stop_count: int
    blocks: list[BlockOut]
    stops: list[StopOut]
