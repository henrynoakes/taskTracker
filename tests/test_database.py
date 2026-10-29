import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tasktracker import database as db
from tasktracker.models import Task


def test_connect_database_uses_named_rows() -> None:
    connection = db.connect_database(":memory:")
    try:
        assert connection.row_factory is sqlite3.Row
        row = connection.execute("SELECT 42 AS answer").fetchone()
        assert row["answer"] == 42
    finally:
        connection.close()


def test_connect_database_invalid_path(tmp_path: Path) -> None:
    with pytest.raises(sqlite3.OperationalError):
        db.connect_database(str(tmp_path / "missing" / "tasks.db"))


def test_initialize_database_is_idempotent(connection: sqlite3.Connection) -> None:
    with connection:
        task_id = db.insert_task(connection, "Keep me", 1, 1)
    before = db.find_task(connection, task_id)
    db.initialize_database(connection)
    assert db.find_task(connection, task_id) == before
    assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1


def test_initialize_database_migrates_existing_tasks() -> None:
    connection = db.connect_database(":memory:")
    try:
        with connection:
            connection.execute(
                "CREATE TABLE tasks (id INTEGER PRIMARY KEY, name TEXT, priority INTEGER, "
                "duration INTEGER, due_date TEXT, created_at TEXT, completed INTEGER)"
            )
            connection.execute(
                "INSERT INTO tasks VALUES "
                "(1, 'Existing', 2, 3, '2026-11-10', '2026-10-01T12:00:00+00:00', 0)"
            )
            db.initialize_database(connection)
            db.initialize_database(connection)
        task = db.find_task(connection, 1)
        assert task.name == "Existing"
        assert task.due_date == date(2026, 11, 10)
        assert task.scheduled_date is None
        with connection:
            db.update_task(connection, replace(task, scheduled_date=date(2026, 11, 1)))
        assert db.find_task(connection, 1).scheduled_date == date(2026, 11, 1)
    finally:
        connection.close()


@pytest.mark.parametrize("scheduled_date", [None, date(2026, 11, 1)])
def test_scheduled_date_storage_and_filtering(
    connection: sqlite3.Connection, scheduled_date: date | None,
) -> None:
    with connection:
        task_id = db.insert_task(connection, "Scheduled", 2, 3, scheduled_date=scheduled_date)
    task = db.find_task(connection, task_id)
    assert task.scheduled_date == scheduled_date
    assert connection.execute(
        "SELECT scheduled_date FROM tasks WHERE id = ?", (task_id,),
    ).fetchone()[0] == (scheduled_date.isoformat() if scheduled_date else None)
    assert db.list_tasks(connection, "scheduled_date", scheduled_date) == [task]
    for value in (date(2026, 12, 1), None):
        task = replace(task, scheduled_date=value)
        with connection:
            assert db.update_task(connection, task) is True
        assert db.find_task(connection, task_id) == task
        assert db.task_to_params(task)["scheduled_date"] == (value.isoformat() if value else None)


@pytest.mark.parametrize("due_date", [None, date(2026, 11, 10)])
@pytest.mark.parametrize("completed", [False, True])
def test_row_to_task(due_date: date | None, completed: bool) -> None:
    connection = db.connect_database(":memory:")
    created_at = datetime(2026, 10, 1, 12, tzinfo=timezone(timedelta(hours=2)))
    try:
        row = connection.execute(
            "SELECT 7 AS id, 'Physics' AS name, 2 AS priority, 4 AS duration, "
            "? AS due_date, ? AS created_at, ? AS completed, NULL AS scheduled_date, NULL AS description",
            (due_date.isoformat() if due_date else None, created_at.isoformat(), int(completed)),
        ).fetchone()
        assert db.row_to_task(row) == Task(
            id=7, name="Physics", priority=2, duration=4,
            due_date=due_date, created_at=created_at, completed=completed,
        )
        assert type(db.row_to_task(row).completed) is bool
    finally:
        connection.close()


@pytest.mark.parametrize(
    "due_date, created_at",
    [("invalid", "2026-10-01T12:00:00+00:00"), (None, "invalid")],
)
def test_row_to_task_rejects_invalid_dates(
    connection: sqlite3.Connection, due_date: str | None, created_at: str,
) -> None:
    row = connection.execute(
        "SELECT 1 AS id, 'Task' AS name, 1 AS priority, 1 AS duration, "
        "? AS due_date, ? AS created_at, 0 AS completed, NULL AS scheduled_date, NULL AS description", (due_date, created_at),
    ).fetchone()
    with pytest.raises(ValueError):
        db.row_to_task(row)


@pytest.mark.parametrize("due_date", [None, date(2026, 11, 10)])
@pytest.mark.parametrize("completed", [False, True])
def test_task_to_params(due_date: date | None, completed: bool) -> None:
    created_at = datetime(2026, 10, 1, 12, tzinfo=UTC)
    task = Task(
        id=7, name="Physics", priority=2, duration=4,
        created_at=created_at, due_date=due_date, completed=completed,
    )
    params = db.task_to_params(task)
    assert params == {
        "id": 7, "name": "Physics", "priority": 2, "duration": 4,
        "created_at": "2026-10-01T12:00:00+00:00",
        "due_date": "2026-11-10" if due_date else None,
        "completed": 1 if completed else 0,
        "scheduled_date": None,
        "description": None,
    }
    assert type(params["completed"]) is int


@pytest.mark.parametrize("due_date", [None, date(2026, 11, 10)])
def test_insert_task(connection: sqlite3.Connection, due_date: date | None) -> None:
    before = datetime.now(UTC)
    with connection:
        task_id = db.insert_task(connection, "日本語 ' ; DROP TABLE tasks; --", 5, 10, due_date)
    after = datetime.now(UTC)
    row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    assert type(task_id) is int
    assert row["name"] == "日本語 ' ; DROP TABLE tasks; --"
    assert row["priority"] == 5
    assert row["duration"] == 10
    assert row["due_date"] == (due_date.isoformat() if due_date else None)
    assert row["completed"] == 0
    created_at = datetime.fromisoformat(row["created_at"])
    assert created_at.tzinfo is UTC
    assert before <= created_at <= after
    assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1


def test_insert_generates_distinct_ids(connection: sqlite3.Connection) -> None:
    with connection:
        first = db.insert_task(connection, "Same name", 1, 1)
    with connection:
        second = db.insert_task(connection, "Same name", 1, 1)
    assert first != second
    assert db.find_task(connection, first).name == "Same name"
    assert db.find_task(connection, second).name == "Same name"


def test_find_task(connection: sqlite3.Connection, task_ids: tuple[int, int]) -> None:
    task = db.find_task(connection, task_ids[1])
    assert isinstance(task, Task)
    assert task.id == task_ids[1]
    assert task.name == "Physics"
    assert task.priority == 2
    assert task.duration == 4
    assert task.due_date == date(2026, 11, 10)
    assert task.completed is False


@pytest.mark.parametrize("task_id", [-1, 0, 999])
def test_find_missing_task(connection: sqlite3.Connection, task_id: int) -> None:
    assert db.find_task(connection, task_id) is None


@pytest.mark.parametrize("due_date", [None, date(2027, 1, 1)])
def test_update_task_preserves_id_creation_time_and_other_rows(
    connection: sqlite3.Connection, task_ids: tuple[int, int], due_date: date | None,
) -> None:
    first, second = task_ids
    original = db.find_task(connection, second)
    other = db.find_task(connection, first)
    updated = replace(
        original, name="Updated", priority=5, duration=10,
        due_date=due_date,
    )
    # created_at is immutable in storage even if the caller changes its snapshot.
    supplied = replace(updated, created_at=datetime(2000, 1, 1, tzinfo=UTC))
    with connection:
        assert db.update_task(connection, supplied) is True
    assert db.find_task(connection, second) == updated
    assert db.find_task(connection, first) == other
    with connection:
        assert db.update_task(connection, updated) is True


def test_update_missing_task_does_not_insert(connection: sqlite3.Connection) -> None:
    task = Task(id=999, name="Missing", priority=1, duration=1, created_at=datetime.now(UTC))
    with connection:
        assert db.update_task(connection, task) is False
    assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_delete_task(connection: sqlite3.Connection, task_ids: tuple[int, int]) -> None:
    first, second = task_ids
    other = db.find_task(connection, second)
    with connection:
        assert db.delete_task(connection, first) is True
    assert db.find_task(connection, first) is None
    assert db.find_task(connection, second) == other
    with connection:
        assert db.delete_task(connection, first) is False


def test_delete_missing_task_from_empty_database(connection: sqlite3.Connection) -> None:
    with connection:
        assert db.delete_task(connection, 999) is False


@pytest.mark.parametrize(
    "field, value",
    [("name", None), ("priority", None), ("duration", None),
     ("created_at", None), ("completed", None),
     ("priority", 0), ("priority", 6), ("duration", 0),
     ("duration", 11), ("completed", -1), ("completed", 2)],
)
def test_schema_rejects_constraint_violations(
    connection: sqlite3.Connection, field: str, value: object,
) -> None:
    values = dict(name="Task", priority=1, duration=1, created_at="2026-10-01T12:00:00+00:00", completed=0)
    values[field] = value
    with pytest.raises(sqlite3.IntegrityError):
        with connection:
            connection.execute(
                "INSERT INTO tasks (name, priority, duration, created_at, completed) "
                "VALUES (:name, :priority, :duration, :created_at, :completed)", values,
            )
    assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


@pytest.mark.parametrize("priority, duration", [(0, 1), (6, 1), (1, 0), (1, 11)])
def test_invalid_update_preserves_stored_task(
    connection: sqlite3.Connection, task_ids: tuple[int, int], priority: int, duration: int,
) -> None:
    original = db.find_task(connection, task_ids[0])
    with pytest.raises(sqlite3.IntegrityError):
        with connection:
            db.update_task(connection, replace(original, priority=priority, duration=duration))
    assert db.find_task(connection, task_ids[0]) == original


@pytest.mark.parametrize("operation", ["insert", "update", "delete"])
def test_changes_persist_after_reconnecting(tmp_path: Path, operation: str) -> None:
    path = str(tmp_path / "tasks.db")
    connection = db.connect_database(path)
    try:
        with connection:
            db.initialize_database(connection)
            task_id = db.insert_task(connection, "Original", 1, 3, date(2026, 11, 10))
        expected = db.find_task(connection, task_id)
        with connection:
            if operation == "update":
                expected = replace(expected, name="Saved change", due_date=None)
                assert db.update_task(connection, expected) is True
            elif operation == "delete":
                assert db.delete_task(connection, task_id) is True
                expected = None
    finally:
        connection.close()

    reopened = db.connect_database(path)
    try:
        assert db.find_task(reopened, task_id) == expected
    finally:
        reopened.close()


@pytest.mark.parametrize("operation", ["insert", "update", "delete"])
@pytest.mark.parametrize("failure", ["constraint", "application"])
def test_failed_transaction_rolls_back_changes_after_reconnecting(
    tmp_path: Path, operation: str, failure: str,
) -> None:
    path = str(tmp_path / "tasks.db")
    connection = db.connect_database(path)
    try:
        with connection:
            db.initialize_database(connection)
            task_id = db.insert_task(connection, "Original", 1, 3)
            other_id = db.insert_task(connection, "Unrelated", 2, 4)
        original = db.find_task(connection, task_id)
        other = db.find_task(connection, other_id)
        inserted_id = None

        error = sqlite3.IntegrityError if failure == "constraint" else RuntimeError
        with pytest.raises(error):
            with connection:
                if operation == "insert":
                    inserted_id = db.insert_task(connection, "Temporary", 1, 1)
                    assert db.find_task(connection, inserted_id) is not None
                elif operation == "update":
                    assert db.update_task(connection, replace(original, name="Temporary")) is True
                    assert db.find_task(connection, task_id).name == "Temporary"
                else:
                    assert db.delete_task(connection, task_id) is True
                    assert db.find_task(connection, task_id) is None

                if failure == "constraint":
                    db.insert_task(connection, "Invalid priority", 6, 1)
                else:
                    raise RuntimeError("Failure after a successful write")

        assert connection.in_transaction is False
        assert db.find_task(connection, task_id) == original
        assert db.find_task(connection, other_id) == other
        assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 2
        if inserted_id is not None:
            assert db.find_task(connection, inserted_id) is None
    finally:
        connection.close()

    reopened = db.connect_database(path)
    try:
        assert db.find_task(reopened, task_id) == original
        assert db.find_task(reopened, other_id) == other
        assert reopened.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 2
    finally:
        reopened.close()
