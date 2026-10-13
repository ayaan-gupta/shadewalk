from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shadewalk.config import Settings
from shadewalk.main import create_app
from shadewalk.store import Dataset, FileStore


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(DATABASE_URL="", WEATHER_PROVIDER="offline")


@pytest.fixture(scope="session")
def data(settings: Settings) -> Dataset:
    return FileStore(settings.data_dir).load()


@pytest.fixture(scope="session")
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))
