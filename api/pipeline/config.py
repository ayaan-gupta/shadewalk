"""The pilot area and every modelling constant the pipeline uses, in one place."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "raw"
OUT = REPO / "data" / "pilot"


@dataclass(frozen=True)
class Pilot:
    slug: str
    name: str
    # west, south, east, north in degrees
    bbox: tuple[float, float, float, float]
    timezone: str
    # Obstacles this far outside the walking area still cast shadows into it.
    buffer_m: float = 400.0
    grid_res_m: float = 1.0

    @property
    def centre(self) -> tuple[float, float]:
        w, s, e, n = self.bbox
        return ((s + n) / 2, (w + e) / 2)


PILOT = Pilot(
    slug="downtown-dallas",
    name="Downtown Dallas and the Arts District",
    bbox=(-96.8060, 32.7765, -96.7935, 32.7905),
    timezone="America/Chicago",
)

# Building heights. OSM `height` wins, then levels, then the default.
METRES_PER_LEVEL = 3.0
DEFAULT_BUILDING_HEIGHT_M = 10.0

# Canopy. Heights come from lidar where it is believable, else the PRD's 8 m.
DEFAULT_CANOPY_HEIGHT_M = 8.0
MIN_CANOPY_HEIGHT_M = 3.0
MAX_CANOPY_HEIGHT_M = 30.0

# The shade table: one representative day per month, every hour, local time.
REFERENCE_YEAR = 2025
REPRESENTATIVE_DAY = 15
SUN_SLOT_MINUTES = 15
# Below this the sun is behind the skyline in any real street; call it shade.
MIN_SUN_ELEVATION_DEG = 2.0
SAMPLE_SPACING_M = 1.0

NAIP_COLLECTION = "naip"
STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
