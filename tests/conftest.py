import sqlite3
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tasktracker import api, scheduler
from tasktracker import database as db
from tasktracker import operations as ops


@pytest.fixture
def freeze_time(monkeypatch: pytest.MonkeyPatch):
    def freeze(instant: datetime) -> None:
        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return instant.astimezone(tz)

        monkeypatch.setattr(ops, "datetime", FrozenDatetime)
        monkeypatch.setattr(scheduler, "datetime", FrozenDatetime)
    return freeze


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(api, "database_path", tmp_path / "tasks.db")
    with TestClient(api.app) as client:
        yield client


@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    connection = db.connect_database(":memory:")
    try:
        with connection:
            db.initialize_database(connection)
        yield connection
    finally:
        connection.close()


@pytest.fixture
def task_ids(connection: sqlite3.Connection) -> tuple[int, int]:
    with connection:
        first = db.insert_task(connection, "Maths", 1, 3)
        second = db.insert_task(connection, "Physics", 2, 4, date(2026, 11, 10))
    return first, second
