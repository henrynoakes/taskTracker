import sqlite3
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from . import database as db
from .models import Task, WorkLogEntry
from .validation import (
    validate_due_date,
    validate_duration,
    validate_fields,
    validate_name,
    validate_priority,
    validate_scheduled_date,
    validators,
)

UK_TIMEZONE = ZoneInfo("Europe/London")


def add_task(  # A wrapper for insert_task
    connection: sqlite3.Connection,
    name: str,
    priority: int,
    duration: int,
    due_date: date | None = None,
    scheduled_date: date | None = None,
) -> int:
    validate_name(name)
    validate_priority(priority)
    validate_duration(duration)
    validate_due_date(due_date)
    validate_scheduled_date(scheduled_date)

    return db.insert_task(
        connection,
        name,
        priority,
        duration,
        due_date,
        scheduled_date,
    )


class TaskNotFoundError(LookupError):
    pass


def find_task(
    database: sqlite3.Connection, task_id: int
) -> Task | None:  # Wrapper of db.find_task which allows for task to not exist
    return db.find_task(database, task_id)


def get_task(  # Wrapper of db.find_task which raises an error if task not found
    database: sqlite3.Connection, task_id: int
) -> Task:
    task = db.find_task(database, task_id)
    if task is None:
        raise TaskNotFoundError(f"Task with id {task_id} was not found")
    return task


def list_tasks(
    database: sqlite3.Connection,
    field: str | None = None,
    value: object = None,
    sort_by: str | None = None,
    descending: bool = False,
) -> list[Task]:
    return db.list_tasks(
        database,
        field,
        value,
        sort_by,
        descending,
    )


def complete_task(database: sqlite3.Connection, task_id: int) -> bool:
    """Complete and log once; the caller must manage the transaction."""
    # Updating first acquires SQLite's write lock before reading the snapshot.
    # Concurrent completion requests cannot both perform this transition.
    changed = db.mark_task_completed(database, task_id)
    task = db.find_task(database, task_id)
    if task is None:
        return False
    if changed:
        now = datetime.now(UK_TIMEZONE)
        db.insert_work_log(
            database,
            task.id,
            task.name,
            now.date(),
            now.astimezone(UTC),
            task.duration,
        )
    return True


def edit_task(  # Wrapper of db.edit_task
    database: sqlite3.Connection, task_id: int, field: str, value: object
) -> bool:
    validate_fields(field)
    validators[field](value)
    if field in {"due_date", "scheduled_date"} and type(value) is date:
        value = value.isoformat()

    return db.edit_task(database, task_id, field, value)


def delete_task(  # Just a wrapper for delete_task_db
    database: sqlite3.Connection,
    task_id: int,
) -> bool:
    return db.delete_task(database, task_id)


def list_work_log(
    database: sqlite3.Connection,
    work_date: date | None = None,
) -> list[WorkLogEntry]:
    return db.list_work_log(database, work_date)


def get_work_duration(database: sqlite3.Connection, work_date: date) -> int:
    return db.get_work_duration(database, work_date)


def get_work_log_summary(database: sqlite3.Connection) -> list[dict[str, str | int]]:
    return db.get_work_log_summary(database)
