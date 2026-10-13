"""Sun positions from pvlib for the representative day of each month."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from pvlib import solarposition

from .config import PILOT, REFERENCE_YEAR, REPRESENTATIVE_DAY, SUN_SLOT_MINUTES


def sun_position(when: datetime, lat: float, lon: float) -> tuple[float, float]:
    """(azimuth, apparent elevation) in degrees for one timezone-aware moment. Azimuth is clockwise from north."""
    pos = solarposition.get_solarposition(pd.DatetimeIndex([when]), lat, lon)
    return float(pos["azimuth"].iloc[0]), float(pos["apparent_elevation"].iloc[0])


def sun_table() -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Azimuth and elevation as [12 months, slots per day] arrays in local clock time."""
    lat, lon = PILOT.centre
    tz = ZoneInfo(PILOT.timezone)
    slots = 24 * 60 // SUN_SLOT_MINUTES
    times = [
        datetime(REFERENCE_YEAR, month, REPRESENTATIVE_DAY, tzinfo=tz) + timedelta(minutes=SUN_SLOT_MINUTES * slot)
        for month in range(1, 13)
        for slot in range(slots)
    ]
    pos = solarposition.get_solarposition(pd.DatetimeIndex(times), lat, lon)
    azimuth = pos["azimuth"].to_numpy(dtype=np.float32).reshape(12, slots)
    elevation = pos["apparent_elevation"].to_numpy(dtype=np.float32).reshape(12, slots)
    return azimuth, elevation
