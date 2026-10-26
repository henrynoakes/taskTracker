import sqlite3
from datetime import UTC, date, datetime
from .models import Task


# The row format:
# id
# name
# priority
# duration
# due_date
# created_at
# completed


def connect_database(path: str) -> sqlite3.Connection:
    database = sqlite3.connect(path)
    database.row_factory = sqlite3.Row
    return database


def initialize_database(database: sqlite3.Connection) -> None:
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 5),
            duration INTEGER NOT NULL CHECK (duration BETWEEN 1 AND 10),
            due_date TEXT,
            created_at TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1))
        )
        """
    )


def row_to_task(row: sqlite3.Row) -> Task:
    task = Task(
        id=row["id"],
        name=row["name"],
        priority=row["priority"],
        duration=row["duration"],
        due_date=date.fromisoformat(row["due_date"])
        if row["due_date"] is not None
        else None,  # Allows for due date to be None
        created_at=datetime.fromisoformat(row["created_at"]),
        completed=bool(row["completed"]),
    )

    return task


def task_to_params(task: Task) -> dict[str, object]:
    return {
        "id": task.id,
        "name": task.name,
        "priority": task.priority,
        "duration": task.duration,
        "due_date": task.due_date.isoformat() if task.due_date is not None else None,
        "created_at": task.created_at.isoformat(),
        "completed": int(task.completed),
    }


def insert_task(
    database: sqlite3.Connection,
    name: str,
    priority: int,
    duration: int,
    due_date: date | None = None,
) -> int:
    created_at = datetime.now(UTC)
    cursor = database.execute(
        """ 
        INSERT INTO tasks (
            name,
            priority,
            duration,
            due_date,
            created_at,
            completed
        )
        VALUES (
            :name,
            :priority,
            :duration,
            :due_date,
            :created_at,
            :completed
        )
        """,
        {
            "name": name,
            "priority": priority,
            "duration": duration,
            "due_date": due_date.isoformat() if due_date is not None else None,
            "created_at": created_at.isoformat(),
            "completed": 0,
        },
    )

    task_id = cursor.lastrowid

    if task_id is None:
        raise RuntimeError("SQLite did not generate a task ID")

    return task_id


def update_task(database: sqlite3.Connection, task: Task) -> bool:
    cursor = database.execute(
        """
        UPDATE tasks
        SET
            name = :name,
            priority = :priority,
            duration = :duration,
            due_date = :due_date,
            completed = :completed
        WHERE id = :id
        """,
        task_to_params(task),
    )

    return cursor.rowcount > 0


def find_task(database: sqlite3.Connection, task_id: int) -> Task | None:
    cursor = database.execute(
        "SELECT * FROM tasks WHERE id = ?",
        (task_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return row_to_task(row)


def delete_task(
    database: sqlite3.Connection,
    task_id: int,
) -> bool:
    cursor = database.execute(
        "DELETE FROM tasks WHERE id = ?",
        (task_id,),
    )

    return cursor.rowcount > 0  # Returns true if the nuber of deleted rows is > 0
