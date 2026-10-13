"""Runtime settings, all from the environment. See .env.example."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO / ".env", extra="ignore")

    data_dir: Path = Field(default=REPO / "data" / "pilot", alias="SHADEWALK_DATA_DIR")
    # Empty means "serve straight from the committed files".
    database_url: str = Field(default="", alias="DATABASE_URL")
    weather_provider: Literal["offline", "open-meteo"] = Field(default="offline", alias="WEATHER_PROVIDER")
    weather_timeout_s: float = Field(default=4.0, alias="WEATHER_TIMEOUT_S")
    walk_speed_mps: float = Field(default=1.3, alias="WALK_SPEED_MPS", gt=0.2, lt=3.0)
    cors_origins: str = Field(default="http://localhost:4107,http://127.0.0.1:4107", alias="CORS_ORIGINS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
