from pathlib import Path
import sqlite3
from fastapi import FastAPI, HTTPException, Depends
from collections.abc import Generator
from contextlib import asynccontextmanager
from typing import Annotated
from .schemas import TaskCreate, TaskUpdate
from . import database as db
from . import operations as ops

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


@app.get("/tasks")
def list_tasks(
    connection: database_connection,
):
    return ops.list_tasks(connection)


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
            )

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


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    connection: database_connection,
):
    with connection:
        deleted = ops.delete_task(connection, task_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        )
