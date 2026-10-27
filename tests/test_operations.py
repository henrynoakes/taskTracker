from collections.abc import Callable
from datetime import UTC, date, datetime
import sqlite3
from typing import Any

import pytest

from tasktracker import database as db
from tasktracker import operations as ops
from tasktracker.models import Task


def snapshot(connection: sqlite3.Connection) -> list[tuple]:
    return [tuple(row) for row in connection.execute("SELECT * FROM tasks ORDER BY id")]


@pytest.mark.parametrize("due_date", [None, date(2026, 12, 1)])
@pytest.mark.parametrize("scheduled_date", [None, date(2026, 11, 1)])
def test_add_task(
    connection: sqlite3.Connection, due_date: date | None, scheduled_date: date | None,
) -> None:
    before = datetime.now(UTC)
    with connection:
        task_id = ops.add_task(connection, "Chemistry", 5, 10, due_date, scheduled_date)
    after = datetime.now(UTC)
    task = ops.get_task(connection, task_id)

    assert type(task_id) is int
    assert task.name == "Chemistry"
    assert task.priority == 5
    assert task.duration == 10
    assert task.due_date == due_date
    assert task.scheduled_date == scheduled_date
    assert task.completed is False
    assert task.created_at.tzinfo is UTC
    assert before <= task.created_at <= after


@pytest.mark.parametrize(
    "field, value, error",
    [
        ("name", " ", ValueError), ("name", None, TypeError),
        ("priority", 0, ValueError), ("priority", 6, ValueError),
        ("priority", True, TypeError), ("duration", 0, ValueError),
        ("duration", 11, ValueError), ("duration", 1.5, TypeError),
        ("due_date", "2026-11-10", TypeError),
        ("due_date", datetime(2026, 11, 10), TypeError),
        ("scheduled_date", "2026-11-10", TypeError),
        ("scheduled_date", datetime(2026, 11, 10), TypeError),
    ],
)
def test_invalid_add_leaves_database_unchanged(
    connection: sqlite3.Connection, task_ids: tuple[int, int],
    field: str, value: object, error: type[Exception],
) -> None:
    original = snapshot(connection)
    values: dict[str, Any] = dict(name="Chemistry", priority=3, duration=2, due_date=None)
    values[field] = value

    with pytest.raises(error):
        with connection:
            ops.add_task(connection, **values)

    assert snapshot(connection) == original


def test_get_task(connection: sqlite3.Connection, task_ids: tuple[int, int]) -> None:
    task = ops.get_task(connection, task_ids[1])
    assert isinstance(task, Task)
    assert task.id == task_ids[1]
    assert task.name == "Physics"
    assert task.due_date == date(2026, 11, 10)


def test_get_missing_task(connection: sqlite3.Connection) -> None:
    with pytest.raises(ops.TaskNotFoundError, match="Task with id 999 was not found"):
        ops.get_task(connection, 999)


def test_complete_task_changes_only_completed(
    connection: sqlite3.Connection, task_ids: tuple[int, int],
) -> None:
    first, second = task_ids
    expected = ops.get_task(connection, first)
    other = ops.get_task(connection, second)
    expected.completed = True

    with connection:
        assert ops.complete_task(connection, first) is True
    assert ops.get_task(connection, first) == expected
    assert ops.get_task(connection, second) == other
    with connection:
        assert ops.complete_task(connection, first) is True
    assert ops.get_task(connection, first) == expected


@pytest.mark.parametrize(
    "field, value",
    [("name", "日本語 ' ; DROP TABLE tasks; --"), ("priority", 5),
     ("duration", 10), ("due_date", date(2026, 12, 1)),
     ("due_date", None), ("scheduled_date", date(2026, 11, 1)),
     ("scheduled_date", None), ("completed", True), ("completed", False)],
)
def test_edit_changes_only_requested_field(
    connection: sqlite3.Connection, task_ids: tuple[int, int], field: str, value: object,
) -> None:
    first, second = task_ids
    if field == "completed" and value is False:
        with connection:
            ops.complete_task(connection, second)
    expected = ops.get_task(connection, second)
    other = ops.get_task(connection, first)
    setattr(expected, field, value)

    with connection:
        assert ops.edit_task(connection, second, field, value) is True
    assert ops.get_task(connection, second) == expected
    assert ops.get_task(connection, first) == other


@pytest.mark.parametrize(
    "field, value, error",
    [("name", "", ValueError), ("name", None, TypeError),
     ("priority", 0, ValueError), ("priority", True, TypeError),
     ("duration", 11, ValueError), ("duration", "2", TypeError),
     ("due_date", "2026-11-10", TypeError),
     ("scheduled_date", "2026-11-10", TypeError), ("completed", 1, TypeError),
     ("id", 10, ValueError), ("created_at", None, ValueError),
     ("unknown", "value", ValueError)],
)
def test_invalid_edit_leaves_database_unchanged(
    connection: sqlite3.Connection, task_ids: tuple[int, int],
    field: str, value: object, error: type[Exception],
) -> None:
    original = snapshot(connection)
    with pytest.raises(error):
        with connection:
            ops.edit_task(connection, task_ids[0], field, value)
    assert snapshot(connection) == original


def test_edit_validates_before_lookup(connection: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="Priority must be between 1 and 5"):
        with connection:
            ops.edit_task(connection, 999, "priority", 0)


def test_delete_task(connection: sqlite3.Connection, task_ids: tuple[int, int]) -> None:
    first, second = task_ids
    other = ops.get_task(connection, second)
    with connection:
        assert ops.delete_task(connection, first) is True
    assert db.find_task(connection, first) is None
    assert ops.get_task(connection, second) == other
    with connection:
        assert ops.delete_task(connection, first) is False


@pytest.mark.parametrize("seeded", [False, True])
@pytest.mark.parametrize("operation", [ops.complete_task, ops.delete_task])
def test_missing_task_does_not_change_database(
    connection: sqlite3.Connection, seeded: bool,
    operation: Callable[[sqlite3.Connection, int], bool],
) -> None:
    if seeded:
        with connection:
            ops.add_task(connection, "Existing", 1, 1)
    original = snapshot(connection)
    assert operation(connection, 999) is False
    assert snapshot(connection) == original


@pytest.mark.parametrize("seeded", [False, True])
def test_edit_missing_task(connection: sqlite3.Connection, seeded: bool) -> None:
    if seeded:
        with connection:
            ops.add_task(connection, "Existing", 1, 1)
    original = snapshot(connection)
    with connection:
        assert ops.edit_task(connection, 999, "name", "Updated") is False
    assert snapshot(connection) == original


@pytest.mark.parametrize("failure", ["add", "edit", "missing_task", "application"])
def test_failed_operation_rolls_back_all_changes(
    connection: sqlite3.Connection, task_ids: tuple[int, int], failure: str,
) -> None:
    first, second = task_ids
    original = snapshot(connection)
    error = {
        "add": ValueError,
        "edit": ValueError,
        "missing_task": ops.TaskNotFoundError,
        "application": RuntimeError,
    }[failure]

    with pytest.raises(error):
        with connection:
            added_id = ops.add_task(connection, "Temporary", 1, 1)
            assert ops.edit_task(connection, first, "name", "Temporary name") is True
            assert ops.complete_task(connection, first) is True
            assert ops.delete_task(connection, second) is True
            assert ops.get_task(connection, added_id).name == "Temporary"
            assert ops.get_task(connection, first).completed is True
            assert db.find_task(connection, second) is None

            if failure == "add":
                ops.add_task(connection, "Invalid", 6, 1)
            elif failure == "edit":
                ops.edit_task(connection, first, "duration", 0)
            elif failure == "missing_task":
                ops.get_task(connection, 999)
            else:
                raise RuntimeError("Failure after successful operations")

    assert connection.in_transaction is False
    assert snapshot(connection) == original

    # The same connection remains usable after rollback.
    with connection:
        assert ops.edit_task(connection, first, "name", "Recovered") is True
    assert ops.get_task(connection, first).name == "Recovered"


def test_successful_transaction_commits_all_operations(
    connection: sqlite3.Connection, task_ids: tuple[int, int],
) -> None:
    first, second = task_ids
    with connection:
        added_id = ops.add_task(connection, "New task", 2, 3)
        assert ops.edit_task(connection, first, "name", "Saved name") is True
        assert ops.complete_task(connection, first) is True
        assert ops.delete_task(connection, second) is True

    # A later rollback must not undo the completed transaction.
    connection.rollback()
    assert ops.get_task(connection, added_id).name == "New task"
    assert ops.get_task(connection, first).name == "Saved name"
    assert ops.get_task(connection, first).completed is True
    assert db.find_task(connection, second) is None


def test_missing_task_false_result_does_not_trigger_rollback(
    connection: sqlite3.Connection,
) -> None:
    # Transaction rollback requires an exception to leave the context.
    with connection:
        added_id = ops.add_task(connection, "Saved", 1, 1)
        assert ops.complete_task(connection, 999) is False
        assert ops.edit_task(connection, 999, "name", "Missing") is False
        assert ops.delete_task(connection, 999) is False

    connection.rollback()
    assert ops.get_task(connection, added_id).name == "Saved"
