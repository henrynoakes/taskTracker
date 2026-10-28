import sqlite3
from collections.abc import Generator
from pathlib import Path
from typing import Annotated

from fastapi import Depends

from . import database as db

database_path = Path(__file__).resolve().parent.parent / "tasks.db"


def get_connection() -> Generator[sqlite3.Connection, None, None]:
    connection = db.connect_database(str(database_path))

    try:
        yield connection

    finally:
        connection.close()


database_connection = Annotated[
    sqlite3.Connection,
    Depends(get_connection),
]
