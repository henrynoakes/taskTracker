from pathlib import Path
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
# scheduled_date


def connect_database(path: str | Path) -> sqlite3.Connection:
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
            completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
            scheduled_date TEXT
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
        scheduled_date=date.fromisoformat(row["scheduled_date"])
        if row["scheduled_date"] is not None
        else None,  # Allows for scheduled_date to be None
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
        "scheduled_date": task.scheduled_date.isoformat()
        if task.scheduled_date is not None
        else None,
    }


def insert_task(
    database: sqlite3.Connection,
    name: str,
    priority: int,
    duration: int,
    due_date: date | None = None,
    scheduled_date: date | None = None,
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
            completed,
            scheduled_date
        )
        VALUES (
            :name,
            :priority,
            :duration,
            :due_date,
            :created_at,
            :completed,
            :scheduled_date
        )
        """,
        {
            "name": name,
            "priority": priority,
            "duration": duration,
            "due_date": due_date.isoformat() if due_date is not None else None,
            "created_at": created_at.isoformat(),
            "completed": 0,
            "scheduled_date": scheduled_date.isoformat()
            if scheduled_date is not None
            else None,
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
            scheduled_date = :scheduled_date,
            completed = :completed
        WHERE id = :id
        """,
        task_to_params(task),
    )

    return cursor.rowcount > 0


# Add a search_task() which will fuzzy search for task names

editable_columns = {
    "scheduled_date",
    "name",
    "priority",
    "duration",
    "due_date",
    "completed",
}

task_columns = {
    "id",
    "name",
    "priority",
    "duration",
    "due_date",
    "created_at",
    "completed",
    "scheduled_date",
}


def edit_task(
    database: sqlite3.Connection,
    task_id: int,
    field: str,
    value: object,
) -> bool:
    if field not in editable_columns:
        raise ValueError(f"Invalid database column: {field}")

    cursor = database.execute(
        f"UPDATE tasks SET {field} = :value WHERE id = :id",
        {
            "value": value,
            "id": task_id,
        },
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


def list_tasks(
    database: sqlite3.Connection,
    field: str | None = None,
    value: object = None,
) -> list[Task]:

    if field is None:
        rows = database.execute("SELECT * FROM tasks").fetchall()

    else:
        if field not in task_columns:
            raise ValueError(f"Invalid task field: {field}")

        if value is None:
            query = f"SELECT * FROM tasks WHERE {field} IS NULL"
            rows = database.execute(query).fetchall()

        else:
            if isinstance(value, (date, datetime)):
                value = value.isoformat()
            elif isinstance(value, bool):
                value = int(value)

            query = f"SELECT * FROM tasks WHERE {field} = ?"
            rows = database.execute(query, (value,)).fetchall()

    return [row_to_task(row) for row in rows]


def delete_task(
    database: sqlite3.Connection,
    task_id: int,
) -> bool:
    cursor = database.execute(
        "DELETE FROM tasks WHERE id = ?",
        (task_id,),
    )

    return cursor.rowcount > 0  # Returns true if the nuber of deleted rows is > 0
