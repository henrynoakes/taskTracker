from collections.abc import Iterator
from datetime import date
import sqlite3

import pytest

from tasktracker import database as db


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
