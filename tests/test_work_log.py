import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from threading import Barrier

import pytest

from tasktracker import database as db
from tasktracker import operations as ops
from tasktracker.models import WorkLogEntry


@pytest.mark.parametrize(
    "instant, local_date",
    [
        (datetime(2026, 7, 1, 23, 30, tzinfo=UTC), date(2026, 7, 2)),
        (datetime(2026, 1, 1, 23, 30, tzinfo=UTC), date(2026, 1, 1)),
        (datetime(2026, 10, 25, 0, 30, tzinfo=UTC), date(2026, 10, 25)),
        (datetime(2026, 10, 25, 1, 30, tzinfo=UTC), date(2026, 10, 25)),
    ],
)
def test_completion_snapshot_local_date_and_idempotence(connection, freeze_time, instant, local_date):
    freeze_time(instant)
    with connection:
        task_id = ops.add_task(connection, "Maths ' assignment", 1, 3)
        assert ops.complete_task(connection, task_id)
    entries = ops.list_work_log(connection)
    assert entries == [WorkLogEntry(entries[0].id, task_id, "Maths ' assignment", local_date, instant, 3)]
    assert type(entries[0].work_date) is date
    assert entries[0].recorded_at.utcoffset() == timedelta(0)
    assert ops.get_task(connection, task_id).completed
    with connection:
        assert ops.complete_task(connection, task_id)
        assert ops.complete_task(connection, 999) is False
    assert ops.list_work_log(connection) == entries
    assert ops.get_work_duration(connection, local_date) == 3
    # A completed task stays idempotent even on a subsequent date.
    freeze_time(instant + timedelta(days=1))
    with connection:
        assert ops.complete_task(connection, task_id)
    assert ops.list_work_log(connection) == entries


def test_history_survives_edits_deletion_and_reconnection(tmp_path):
    path = tmp_path / "history.db"
    connection = db.connect_database(path)
    try:
        with connection:
            db.initialize_database(connection)
            task_id = ops.add_task(connection, "Original", 1, 3)
            ops.complete_task(connection, task_id)
        original = ops.list_work_log(connection)[0]
        with connection:
            ops.edit_task(connection, task_id, "name", "Renamed")
            ops.edit_task(connection, task_id, "duration", 9)
        assert ops.list_work_log(connection) == [original]
        with connection:
            ops.delete_task(connection, task_id)
        assert ops.list_work_log(connection) == [replace(original, task_id=None)]
    finally:
        connection.close()
    reopened = db.connect_database(path)
    try:
        assert reopened.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert ops.list_work_log(reopened) == [replace(original, task_id=None)]
    finally:
        reopened.close()


def test_work_log_totals_filtering_order_and_constraints(connection):
    today = date(2026, 10, 28)
    now = datetime(2026, 10, 28, 12, tzinfo=UTC)
    with connection:
        later = db.insert_work_log(connection, None, "Later", today, now + timedelta(hours=1), 2)
        first = db.insert_work_log(connection, None, "First", today, now, 3)
        tied = db.insert_work_log(connection, None, "Tied", today, now, 1)
        tomorrow = db.insert_work_log(connection, None, "Tomorrow", today + timedelta(days=1), now + timedelta(days=1), 4)
    assert [entry.id for entry in ops.list_work_log(connection)] == [first, tied, later, tomorrow]
    assert [entry.id for entry in ops.list_work_log(connection, today)] == [first, tied, later]
    assert ops.get_work_duration(connection, today) == 6
    assert ops.get_work_duration(connection, today + timedelta(days=1)) == 4
    assert ops.get_work_duration(connection, today - timedelta(days=1)) == 0
    assert ops.list_work_log(connection, today - timedelta(days=1)) == []
    assert ops.get_work_log_summary(connection) == [
        {"date": "2026-10-28", "duration": 6}, {"date": "2026-10-29", "duration": 4},
    ]
    for task_id, duration in [(999, 1), (None, 0), (None, -1)]:
        with pytest.raises(sqlite3.IntegrityError), connection:
            db.insert_work_log(connection, task_id, "Invalid", today, now, duration)
    with pytest.raises(ValueError, match="timezone-aware"):
        db.insert_work_log(connection, None, "Invalid", today, now.replace(tzinfo=None), 1)


def test_work_log_normalizes_timestamp_offsets(connection):
    today = date(2026, 7, 2)
    instant = datetime(2026, 7, 2, 0, 30, tzinfo=timezone(timedelta(hours=1)))
    with connection:
        db.insert_work_log(connection, None, "Summer", today, instant, 1)
    entry = db.list_work_log(connection)[0]
    assert entry.recorded_at == instant
    assert entry.recorded_at.tzinfo is UTC
    assert entry.work_date == today


@pytest.mark.parametrize("failing_table", ["tasks", "work_log"])
def test_completion_rolls_back_on_database_failure(connection, failing_table):
    with connection:
        task_id = ops.add_task(connection, "Original", 1, 3)
        event = "UPDATE OF completed" if failing_table == "tasks" else "INSERT"
        connection.execute(
            f"CREATE TRIGGER fail_completion BEFORE {event} ON {failing_table} "
            "BEGIN SELECT RAISE(ABORT, 'completion failed'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="completion failed"), connection:
        ops.complete_task(connection, task_id)
    assert not ops.get_task(connection, task_id).completed
    assert ops.list_work_log(connection) == []


def test_completion_does_not_commit_callers_transaction(connection):
    with connection:
        task_id = ops.add_task(connection, "Original", 1, 3)
    with pytest.raises(RuntimeError), connection:
        ops.complete_task(connection, task_id)
        assert len(ops.list_work_log(connection)) == 1
        raise RuntimeError("Roll back the whole operation")
    assert not ops.get_task(connection, task_id).completed
    assert ops.list_work_log(connection) == []


def test_generic_database_updates_preserve_completion(connection):
    with connection:
        task_id = ops.add_task(connection, "Original", 1, 3)
        task = ops.get_task(connection, task_id)
        db.update_task(connection, replace(task, completed=True))
        assert not ops.get_task(connection, task_id).completed
        ops.complete_task(connection, task_id)
        db.update_task(connection, task)
    assert ops.get_task(connection, task_id).completed
    assert len(ops.list_work_log(connection)) == 1
    with pytest.raises(ValueError):
        db.edit_task(connection, task_id, "completed", False)


def test_concurrent_completion_logs_once(tmp_path):
    path = tmp_path / "concurrent.db"
    connection = db.connect_database(path)
    try:
        with connection:
            db.initialize_database(connection)
            task_id = ops.add_task(connection, "Shared", 1, 3)
        barrier = Barrier(2)

        def complete():
            other = db.connect_database(path)
            try:
                barrier.wait(timeout=5)
                with other:
                    return ops.complete_task(other, task_id)
            finally:
                other.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(complete) for _ in range(2)]
            assert [future.result(timeout=10) for future in futures] == [True, True]
        assert len(ops.list_work_log(connection)) == 1
    finally:
        connection.close()


def test_initialize_existing_database_preserves_tasks_and_logs(connection):
    with connection:
        task_id = ops.add_task(connection, "Existing", 1, 2)
        ops.complete_task(connection, task_id)
    task = ops.get_task(connection, task_id)
    entries = ops.list_work_log(connection)
    with connection:
        db.initialize_database(connection)
        db.initialize_database(connection)
    assert ops.get_task(connection, task_id) == task
    assert ops.list_work_log(connection) == entries
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
