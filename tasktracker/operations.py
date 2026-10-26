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


def get_task(  # Wrapper of find_task which raises an error if task not found
    database: sqlite3.Connection, task_id: int
) -> Task:  # For when the task needs to exist. If it doesn't it causes an error.
    task = db.find_task(database, task_id)
    if task is None:
        raise TaskNotFoundError(f"Task with id {task_id} was not found")
    return task


def complete_task(database: sqlite3.Connection, task_id: int) -> bool:
    task = db.find_task(database, task_id)

    if task is None:
        return False

    task.completed = True
    return db.update_task(database, task)


def edit_task(
    database: sqlite3.Connection, task_id: int, field: str, value: object
) -> bool:
    validate_fields(field)
    validators[field](value)

    task = db.find_task(database, task_id)

    if task is None:
        return False

    setattr(task, field, value)
    return db.update_task(database, task)


def delete_task(  # Just a wrapper for delete_task_db
    database: sqlite3.Connection,
    task_id: int,
) -> bool:
    return db.delete_task(database, task_id)
