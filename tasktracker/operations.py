import sqlite3
from datetime import date
from .models import Task
from .validation import (
    validate_due_date,
    validate_duration,
    validate_fields,
    validate_name,
    validate_priority,
    validators,
)
from . import database as db


def add_task(  # A wrapper for insert_task
    connection: sqlite3.Connection,
    name: str,
    priority: int,
    duration: int,
    due_date: date | None = None,
) -> int:
    validate_name(name)
    validate_priority(priority)
    validate_duration(duration)
    validate_due_date(due_date)

    return db.insert_task(
        connection,
        name,
        priority,
        duration,
        due_date,
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


def complete_task(
    database: sqlite3.Connection, task_id: int
) -> bool:  # Wrapper of db.edit_task but only for making "completed" = True
    return db.edit_task(database, task_id, "completed", True)


def edit_task(  # Wrapper of db.edit_task
    database: sqlite3.Connection, task_id: int, field: str, value: object
) -> bool:
    validate_fields(field)
    validators[field](value)
    if field == "due_date" and type(value) is date and value is not None:
        value = value.isoformat()

    return db.edit_task(database, task_id, field, value)


def list_tasks(database: sqlite3.Connection) -> list[Task]:
    return db.list_tasks(database)


def delete_task(  # Just a wrapper for delete_task_db
    database: sqlite3.Connection,
    task_id: int,
) -> bool:
    return db.delete_task(database, task_id)
