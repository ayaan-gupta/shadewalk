"""The HTTP API. `create_app` takes its collaborators as arguments so tests can swap them."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from . import __version__
from .config import Settings, get_settings
from .models import (
    BlockOut,
    Comparison,
    Conditions,
    Leg,
    PlannerResponse,
    RouteOut,
    RouteRequest,
    RouteResponse,
    ShadeResponse,
    SnappedPoint,
    StopOut,
    SunOut,
)
from .overlay import ShadowOverlay
from .planner import rank
from .routing import BASE_DETOUR_CAP, DEFAULT_WEIGHT, MAX_DETOUR_CAP, MAX_WEIGHT, RouteStats, heat_factor, plan
from .shade.table import Sun
from .store import Dataset, DemandRadii, Store, open_store
from .weather import ClimatologyWeather, OpenMeteoWeather, WeatherProvider

# A click this far from any walkable node is outside the pilot.
MAX_SNAP_M = 300.0
LayerParam = Literal["all", "buildings"]


@dataclass
class Runtime:
    settings: Settings
    store: Store
    data: Dataset
    weather: WeatherProvider
    overlay: ShadowOverlay
    static: dict[str, bytes]


def make_weather(settings: Settings) -> WeatherProvider:
    offline = ClimatologyWeather.from_file(settings.data_dir / "climatology.json")
    if settings.weather_provider == "open-meteo":
        return OpenMeteoWeather(fallback=offline, timeout_s=settings.weather_timeout_s)
    return offline


def network_geojson(data: Dataset) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": e.id,
                "properties": {"id": e.id, "kind": e.kind, "street": e.street, "length_m": e.length_m},
                "geometry": {"type": "LineString", "coordinates": e.coords},
            }
            for e in data.network.edges
        ],
    }


def sun_out(sun: Sun) -> SunOut:
    return SunOut(azimuth_deg=round(sun.azimuth_deg, 1), elevation_deg=round(sun.elevation_deg, 1), up=sun.up)


def build_runtime(settings: Settings, store: Store | None = None, weather: WeatherProvider | None = None) -> Runtime:
    store = store or open_store(settings)
    data = store.load()
    overlay = ShadowOverlay(frame=data.frame, grid=data.grid, building=data.building_height, canopy=data.canopy_height, bbox=data.bbox, table=data.shade)
    compact = {"separators": (",", ":")}
    static = {
        "network": json.dumps(network_geojson(data), **compact).encode(),  # type: ignore[arg-type]
        "buildings": json.dumps(data.buildings, **compact).encode(),  # type: ignore[arg-type]
        "canopy": json.dumps(data.canopy, **compact).encode(),  # type: ignore[arg-type]
        "pois": json.dumps([p.__dict__ for p in data.pois], **compact).encode(),  # type: ignore[arg-type]
    }
    return Runtime(settings=settings, store=store, data=data, weather=weather or make_weather(settings), overlay=overlay, static=static)


def create_app(settings: Settings | None = None, store: Store | None = None, weather: WeatherProvider | None = None) -> FastAPI:
    settings = settings or get_settings()
    rt = build_runtime(settings, store, weather)
    data = rt.data
    tz = ZoneInfo(data.meta["timezone"])

    app = FastAPI(title="ShadeWalk", version=__version__)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.state.runtime = rt

    def geojson(key: str) -> Response:
        return Response(content=rt.static[key], media_type="application/json", headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__, "store": rt.store.name, "weather": rt.weather.name, "segments": data.network.edge_count}

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        w, s, e, n = data.bbox
        kinds: dict[str, int] = {}
        for p in data.pois:
            kinds[p.kind] = kinds.get(p.kind, 0) + 1
        return {
            "slug": data.meta["slug"],
            "name": data.meta["name"],
            "bbox": [w, s, e, n],
            "centre": [(w + e) / 2, (s + n) / 2],
            "timezone": data.meta["timezone"],
            "slider": {"min": 0.0, "max": MAX_WEIGHT, "default": DEFAULT_WEIGHT, "base_cap": BASE_DETOUR_CAP, "max_cap": MAX_DETOUR_CAP},
            "walk_speed_mps": settings.walk_speed_mps,
            "store": rt.store.name,
            "weather": rt.weather.name,
            "daylight": [list(data.shade.daylight_minutes(m)) for m in range(1, 13)],
            "overlay": {"corners": rt.overlay.corners(), "slot_minutes": data.shade.sun_slot_minutes},
            "counts": {
                "nodes": data.network.node_count,
                "segments": data.network.edge_count,
                "km": round(float(data.network.lengths.sum()) / 1000, 1),
                "buildings": len(data.buildings["features"]),
                "canopy_patches": len(data.canopy["features"]),
                "pois": kinds,
            },
            "sources": data.meta.get("sources", {}),
            "model": data.meta.get("model", {}),
        }

    @app.get("/api/network")
    def network() -> Response:
        return geojson("network")

    @app.get("/api/buildings")
    def buildings() -> Response:
        return geojson("buildings")

    @app.get("/api/canopy")
    def canopy() -> Response:
        return geojson("canopy")

    @app.get("/api/pois")
    def pois() -> Response:
        return geojson("pois")

    @app.get("/api/shade", response_model=ShadeResponse)
    def shade(
        month: int = Query(ge=1, le=12),
        minute: int = Query(ge=0, le=1439),
        layer: LayerParam = "all",
    ) -> ShadeResponse:
        fractions = data.shade.segments(month, minute, layer)
        lengths = data.network.lengths
        return ShadeResponse(
            month=month,
            minute=minute,
            layer=layer,
            sun=sun_out(data.shade.sun(month, minute)),
            network_shade_pct=round(float((fractions * lengths).sum() / lengths.sum()) * 100, 1),
            shade_pct=np.rint(fractions * 100).astype(int).tolist(),
        )

    @app.get("/api/shadow.png")
    def shadow(
        month: int = Query(ge=1, le=12),
        minute: int = Query(ge=0, le=1439),
        layer: LayerParam = "all",
    ) -> Response:
        step = data.shade.sun_slot_minutes
        png = rt.overlay.render(month, (minute // step) * step, layer)
        return Response(content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})

    def snap(point: Any, label: str) -> SnappedPoint:
        node, dist = data.network.nearest_node(point.lon, point.lat)
        if dist > MAX_SNAP_M:
            raise HTTPException(status_code=422, detail=f"The {label} is {dist:.0f} m from the nearest mapped path. The pilot covers {data.meta['name']} only.")
        return SnappedPoint(lon=float(data.network.node_lon[node]), lat=float(data.network.node_lat[node]), node=node, snapped_m=round(dist, 1))

    def route_out(stats: RouteStats, start: int, fractions: np.ndarray[Any, Any]) -> RouteOut:
        legs: list[Leg] = []
        at = start
        for edge_id in stats.edges:
            edge = data.network.edges[edge_id]
            forward = edge.u == at
            at = edge.v if forward else edge.u
            legs.append(
                Leg(
                    segment_id=edge_id,
                    shade=round(float(fractions[edge_id]), 3),
                    length_m=edge.length_m,
                    street=edge.street,
                    coords=edge.coords if forward else edge.coords[::-1],
                )
            )
        sunny = stats.distance_m - stats.shaded_m
        return RouteOut(
            distance_m=round(stats.distance_m, 1),
            duration_min=round(stats.distance_m / settings.walk_speed_mps / 60, 1),
            shade_pct=round(stats.shade_share * 100, 1),
            shaded_m=round(stats.shaded_m, 1),
            sunny_m=round(sunny, 1),
            sun_min=round(sunny / settings.walk_speed_mps / 60, 1),
            legs=legs,
        )

    @app.post("/api/route", response_model=RouteResponse)
    def route(req: RouteRequest) -> RouteResponse:
        started = time.perf_counter()
        when = req.depart_at.replace(tzinfo=tz)
        month, minute = when.month, when.hour * 60 + when.minute
        origin, destination = snap(req.origin, "start"), snap(req.destination, "destination")
        if origin.node == destination.node:
            raise HTTPException(status_code=422, detail="Start and destination snap to the same point. Pick two places further apart.")

        reading = rt.weather.temperature(origin.lat, origin.lon, when)
        heat = heat_factor(reading.temp_c)
        fractions = data.shade.segments(month, minute, req.layer)
        pair = plan(data.network, fractions, origin.node, destination.node, req.shade_weight, heat)
        if pair is None:
            raise HTTPException(status_code=422, detail="No walkable path connects those two points.")

        shortest = route_out(pair.shortest, origin.node, fractions)
        shadiest = route_out(pair.shadiest, origin.node, fractions)
        return RouteResponse(
            origin=origin,
            destination=destination,
            conditions=Conditions(
                depart_at=when.strftime("%Y-%m-%dT%H:%M"),
                month=month,
                minute=minute,
                sun=sun_out(data.shade.sun(month, minute)),
                temperature_c=reading.temp_c,
                temperature_source=reading.source,
                temperature_detail=reading.detail,
                heat_factor=round(heat, 3),
            ),
            shortest=shortest,
            shadiest=shadiest,
            comparison=Comparison(
                extra_m=round(shadiest.distance_m - shortest.distance_m, 1),
                extra_min=round(shadiest.duration_min - shortest.duration_min, 1),
                shade_gain_points=round(shadiest.shade_pct - shortest.shade_pct, 1),
                sun_min_saved=round(shortest.sun_min - shadiest.sun_min, 1),
                detour_ratio=round(pair.detour_ratio, 3),
                detour_cap=pair.cap,
                capped=pair.capped,
                weight_requested=pair.weight_requested,
                weight_used=round(pair.weight_used, 3),
                same_route=pair.shortest.edges == pair.shadiest.edges,
            ),
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    demand_cache: dict[DemandRadii, Any] = {}

    @app.get("/api/planner", response_model=PlannerResponse)
    def planner(
        month: int = Query(default=7, ge=1, le=12),
        start_hour: int = Query(default=12, ge=0, le=23),
        end_hour: int = Query(default=18, ge=0, le=23),
        layer: LayerParam = "all",
        limit: int = Query(default=40, ge=1, le=200),
    ) -> PlannerResponse:
        if end_hour < start_hour:
            raise HTTPException(status_code=422, detail="end_hour must not be before start_hour")
        radii = DemandRadii()
        if radii not in demand_cache:
            demand_cache[radii] = rt.store.demand(radii)
        result = rank(data.network, data.shade, data.pois, demand_cache[radii], month, start_hour, end_hour, layer, limit)
        mid_lon, mid_lat = data.network.midpoints()
        return PlannerResponse(
            month=month,
            start_hour=start_hour,
            end_hour=end_hour,
            layer=layer,
            store=rt.store.name,
            network_shade_pct=round(result.network_shade * 100, 1),
            low_shade_km=round(result.low_shade_km, 1),
            unshaded_stops=result.unshaded_stops,
            stop_count=result.stop_count,
            blocks=[
                BlockOut(
                    segment_id=b.segment_id,
                    street=b.street,
                    kind=b.kind,
                    length_m=round(b.length_m, 1),
                    shade_pct=round(b.shade * 100, 1),
                    bus_stops=b.bus_stops,
                    rail_stops=b.rail_stops,
                    schools=b.schools,
                    demand=b.demand,
                    priority=round(b.priority, 3),
                    lon=float(mid_lon[b.segment_id]),
                    lat=float(mid_lat[b.segment_id]),
                    coords=data.network.edges[b.segment_id].coords,
                )
                for b in result.blocks
            ],
            stops=[StopOut(id=s.poi.id, kind=s.poi.kind, name=s.poi.name, lon=s.poi.lon, lat=s.poi.lat, shade_pct=round(s.shade * 100, 1)) for s in result.stops],
        )

    return app


def app_factory() -> FastAPI:
    """Entry point for `uvicorn shadewalk.main:app_factory --factory`."""
    return create_app()


def parse_local(text: str, tz: ZoneInfo) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=tz)
