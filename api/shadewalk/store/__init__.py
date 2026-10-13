"""Storage back ends. `open_store` picks PostGIS when DATABASE_URL is set, files otherwise."""

from __future__ import annotations

from ..config import Settings
from .base import Dataset, Demand, DemandRadii, Poi, Store
from .files import FileStore

__all__ = ["Dataset", "Demand", "DemandRadii", "FileStore", "Poi", "Store", "open_store"]


def open_store(settings: Settings) -> Store:
    if settings.database_url:
        from .postgis import PostgisStore

        return PostgisStore(settings.database_url, settings.data_dir)
    return FileStore(settings.data_dir)
