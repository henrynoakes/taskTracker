import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

from .models import Task, WorkLogEntry

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
    database.execute("PRAGMA foreign_keys = ON")
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

    # Upgrade databases created before scheduled_date was introduced.
    columns = {row["name"] for row in database.execute("PRAGMA table_info(tasks)")}
    if "scheduled_date" not in columns:
        database.execute("ALTER TABLE tasks ADD COLUMN scheduled_date TEXT")

    database.execute(
        """
        CREATE TABLE IF NOT EXISTS work_log (
            id INTEGER PRIMARY KEY,
            task_id INTEGER,
            task_name TEXT NOT NULL,
            work_date TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            duration INTEGER NOT NULL CHECK (duration > 0),
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
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
    """Update editable fields while preserving creation time and completion status."""
    cursor = database.execute(
        """
        UPDATE tasks
        SET
            name = :name,
            priority = :priority,
            duration = :duration,
            due_date = :due_date,
            scheduled_date = :scheduled_date
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
    sort_by: str | None = None,
    descending: bool = False,
) -> list[Task]:
    query = "SELECT * FROM tasks"
    params = []

    # Filtering
    if field is not None:
        if field not in task_columns:
            raise ValueError(f"Invalid task field: {field}")

        if value is None:
            query += f" WHERE {field} IS NULL"
        else:
            if isinstance(value, (date, datetime)):
                value = value.isoformat()
            elif isinstance(value, bool):
                value = int(value)

            query += f" WHERE {field} = ?"
            params.append(value)

    # Sorting
    if sort_by is not None:
        if sort_by not in task_columns:
            raise ValueError(f"Invalid sort field: {sort_by}")

        direction = "DESC" if descending else "ASC"

        query += f" ORDER BY {sort_by} IS NULL, {sort_by} {direction}, id ASC"

    rows = database.execute(query, params).fetchall()
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


def mark_task_completed(database: sqlite3.Connection, task_id: int) -> bool:
    """Return whether this transaction changed an incomplete task to completed."""
    cursor = database.execute(
        "UPDATE tasks SET completed = 1 WHERE id = ? AND completed = 0",
        (task_id,),
    )
    return cursor.rowcount > 0


def row_to_work_log_entry(row: sqlite3.Row) -> WorkLogEntry:
    return WorkLogEntry(
        id=row["id"],
        task_id=row["task_id"],
        task_name=row["task_name"],
        work_date=date.fromisoformat(row["work_date"]),
        recorded_at=datetime.fromisoformat(row["recorded_at"]),
        duration=row["duration"],
    )


def insert_work_log(
    database: sqlite3.Connection,
    task_id: int | None,
    task_name: str,
    work_date: date,
    recorded_at: datetime,
    duration: int,
) -> int:
    if recorded_at.utcoffset() is None:
        raise ValueError("Recording timestamp must be timezone-aware")
    cursor = database.execute(
        """
        INSERT INTO work_log (task_id, task_name, work_date, recorded_at, duration)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            task_id,
            task_name,
            work_date.isoformat(),
            recorded_at.astimezone(UTC).isoformat(),
            duration,
        ),
    )
    entry_id = cursor.lastrowid
    if entry_id is None:
        raise RuntimeError("SQLite did not generate a work-log ID")
    return entry_id


def list_work_log(
    database: sqlite3.Connection,
    work_date: date | None = None,
) -> list[WorkLogEntry]:
    if work_date is None:
        rows = database.execute(
            "SELECT * FROM work_log ORDER BY recorded_at, id"
        ).fetchall()
    else:
        rows = database.execute(
            "SELECT * FROM work_log WHERE work_date = ? ORDER BY recorded_at, id",
            (work_date.isoformat(),),
        ).fetchall()
    return [row_to_work_log_entry(row) for row in rows]


def get_work_duration(database: sqlite3.Connection, work_date: date) -> int:
    row = database.execute(
        "SELECT COALESCE(SUM(duration), 0) FROM work_log WHERE work_date = ?",
        (work_date.isoformat(),),
    ).fetchone()
    return int(row[0])


def get_work_log_summary(database: sqlite3.Connection) -> list[dict[str, str | int]]:
    rows = database.execute(
        "SELECT work_date, SUM(duration) AS duration FROM work_log "
        "GROUP BY work_date ORDER BY work_date"
    ).fetchall()
    return [{"date": row["work_date"], "duration": row["duration"]} for row in rows]
