import sqlite3
from collections.abc import Generator
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException

from . import database as db
from . import operations as ops
from . import scheduler
from .schemas import TaskCreate, TaskUpdate

database_path = Path(__file__).resolve().parent.parent / "tasks.db"


@asynccontextmanager
async def lifespan(app: FastAPI):
    connection = db.connect_database(database_path)

    try:
        db.initialize_database(connection)
        connection.commit()
    finally:
        connection.close()

    yield


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

# Creates a FastAPI application and tells it which function to use for startup and shutdown operations.
app = FastAPI(lifespan=lifespan)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Task tracker API"}


@app.get("/tasks/{task_id}")
def get_task(
    task_id: int,
    connection: database_connection,
):
    try:
        return ops.get_task(connection, task_id)

    except ops.TaskNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        ) from None


def parse_filter_value(field: str, value: str) -> object:
    if value == "null":
        return None

    if field in {"id", "priority", "duration"}:
        return int(value)

    if field == "completed":
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        raise ValueError("Completed must be true or false")

    if field in {"due_date", "scheduled_date"}:
        return date.fromisoformat(value)

    if field == "created_at":
        return datetime.fromisoformat(value)

    return value


@app.get("/tasks")
def list_tasks(
    connection: database_connection,
    field: str | None = None,
    value: str | None = None,
):
    if field is None:
        if value is not None:
            raise HTTPException(
                status_code=422,
                detail="A field must be specified when filtering by value",
            )

        return ops.list_tasks(connection)

    if value is None:
        raise HTTPException(
            status_code=422,
            detail="A value must be specified when filtering",
        )

    try:
        if field not in db.task_columns:
            raise ValueError(f"Unknown task field: {field}")
        parsed_value = parse_filter_value(field, value)
        return ops.list_tasks(connection, field, parsed_value)

    except (ValueError, TypeError) as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error


@app.post("/tasks", status_code=201)
def create_task(
    task: TaskCreate,
    connection: database_connection,
):
    try:
        with connection:
            task_id = ops.add_task(
                connection,
                task.name,
                task.priority,
                task.duration,
                task.due_date,
                task.scheduled_date,
            )
            scheduler.schedule_tasks(connection)

    except (ValueError, TypeError) as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    return ops.get_task(connection, task_id)


@app.patch("/tasks/{task_id}")
def update_task(
    task_id: int,
    update: TaskUpdate,
    connection: database_connection,
):
    changes = update.model_dump(exclude_unset=True)

    try:
        ops.get_task(connection, task_id)

        try:
            with connection:
                for field, value in changes.items():
                    ops.edit_task(connection, task_id, field, value)
                scheduler.schedule_tasks(connection)

        except (ValueError, TypeError) as error:
            raise HTTPException(
                status_code=422,
                detail=str(error),
            ) from error

        return ops.get_task(connection, task_id)

    except ops.TaskNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        ) from None


@app.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: int,
    connection: database_connection,
):
    with connection:
        completed = ops.complete_task(connection, task_id)

    if not completed:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        )

    return ops.get_task(connection, task_id)


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    connection: database_connection,
):
    with connection:
        deleted = ops.delete_task(connection, task_id)
        if deleted:
            scheduler.schedule_tasks(connection)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        )


@app.post("/schedule")
def schedule_tasks(connection: database_connection):
    with connection:
        all_scheduled = scheduler.schedule_tasks(connection)

    return {
        "all_scheduled": all_scheduled,
    }


@app.get("/work-log/summary")
def work_log_summary(connection: database_connection):
    return ops.get_work_log_summary(connection)


@app.get("/work-log")
def list_work_log(connection: database_connection, work_date: date | None = None):
    return ops.list_work_log(connection, work_date)
