"""Forecast temperature behind a small interface.

Two providers. `ClimatologyWeather` needs no network: it reads the committed
month-by-hour table of mean temperatures. `OpenMeteoWeather` asks the keyless
Open-Meteo forecast API and falls back to the climatology when the departure
is outside the forecast window or the request fails, so a route is never
blocked on the weather.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 7
CACHE_SECONDS = 1800


@dataclass(frozen=True)
class Temperature:
    temp_c: float
    source: Literal["forecast", "climatology"]
    detail: str


class WeatherProvider(Protocol):
    name: str

    def temperature(self, lat: float, lon: float, when: datetime) -> Temperature:
        """Air temperature at a place and a timezone-aware local time."""
        ...


class ClimatologyWeather:
    """Mean temperature for the calendar month and clock hour, blended between hours."""

    name = "offline"

    def __init__(self, mean_temp_c: list[list[float]], source: str) -> None:
        if len(mean_temp_c) != 12 or any(len(row) != 24 for row in mean_temp_c):
            raise ValueError("climatology must be 12 months by 24 hours")
        self._table = mean_temp_c
        self._source = source

    @staticmethod
    def from_file(path: Path) -> ClimatologyWeather:
        data = json.loads(path.read_text())
        return ClimatologyWeather(data["mean_temp_c"], data["source"])

    def temperature(self, lat: float, lon: float, when: datetime) -> Temperature:
        row = self._table[when.month - 1]
        weight = when.minute / 60
        value = row[when.hour] * (1 - weight) + row[(when.hour + 1) % 24] * weight
        return Temperature(round(value, 1), "climatology", f"typical for the month and hour ({self._source})")


class OpenMeteoWeather:
    """Hourly forecast from Open-Meteo, with the climatology as the safety net."""

    name = "open-meteo"

    def __init__(self, fallback: WeatherProvider, client: httpx.Client | None = None, timeout_s: float = 4.0) -> None:
        self._fallback = fallback
        self._client = client or httpx.Client(timeout=timeout_s)
        self._cache: dict[tuple[float, float], tuple[float, dict[str, float]]] = {}

    def _hourly(self, lat: float, lon: float, tz: str) -> dict[str, float]:
        key = (round(lat, 2), round(lon, 2))
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
        response = self._client.get(
            FORECAST_URL,
            params={"latitude": lat, "longitude": lon, "hourly": "temperature_2m", "timezone": tz, "forecast_days": FORECAST_DAYS},
        )
        response.raise_for_status()
        hourly = parse_hourly(response.json())
        self._cache[key] = (time.monotonic(), hourly)
        return hourly

    def temperature(self, lat: float, lon: float, when: datetime) -> Temperature:
        try:
            hourly = self._hourly(lat, lon, str(when.tzinfo))
            here = hourly.get(when.strftime("%Y-%m-%dT%H:00"))
            if here is None:
                return self._fallback.temperature(lat, lon, when)
            later = hourly.get((when + timedelta(hours=1)).strftime("%Y-%m-%dT%H:00"), here)
            weight = when.minute / 60
            return Temperature(round(here * (1 - weight) + later * weight, 1), "forecast", "Open-Meteo hourly forecast")
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            return self._fallback.temperature(lat, lon, when)


def parse_hourly(payload: dict[str, object]) -> dict[str, float]:
    """Map 'YYYY-MM-DDTHH:00' local timestamps to degrees Celsius."""
    hourly = payload["hourly"]
    if not isinstance(hourly, dict):
        raise ValueError("unexpected Open-Meteo payload")
    return {str(t): float(v) for t, v in zip(hourly["time"], hourly["temperature_2m"]) if v is not None}
