from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import operations as ops
from . import scheduler
from .db_connection import database_connection

router = APIRouter(prefix="/web")

templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")


@router.get("/", response_class=HTMLResponse)
def task_list(request: Request, connection: database_connection):
    tasks = ops.list_tasks(
        connection,
        field="completed",
        value=False,
        sort_by="scheduled_date",
    )

    return templates.TemplateResponse(
        request=request,
        name="tasks.html",
        context={"tasks": tasks},
    )


@router.get("/tasks/new", response_class=HTMLResponse)
def new_task_form(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="task_form.html",
        context={},
    )


@router.post("/tasks/new")
def create_task(
    connection: database_connection,
    name: Annotated[str, Form()],
    priority: Annotated[int, Form()],
    duration: Annotated[int, Form()],
    due_date: Annotated[str, Form()] = "",
):
    parsed_due_date = date.fromisoformat(due_date) if due_date else None

    with connection:
        ops.add_task(
            connection,
            name=name,
            priority=priority,
            duration=duration,
            due_date=parsed_due_date,
        )

        scheduler.schedule_tasks(connection)

    return RedirectResponse(
        url="/web/",
        status_code=303,
    )


@router.post("/tasks/{task_id}/complete")
def complete_task(task_id: int, connection: database_connection):
    with connection:
        completed = ops.complete_task(connection, task_id)

    if not completed:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        )

    return RedirectResponse(
        url="/web/",
        status_code=303,
    )


@router.post("/schedule")
def regenerate_schedule(connection: database_connection):
    with connection:
        scheduler.schedule_tasks(connection)

    return RedirectResponse(
        url="/web/",
        status_code=303,
    )


@router.get("/tasks/{task_id}/edit", response_class=HTMLResponse)
def edit_task_form(request: Request, task_id: int, connection: database_connection):
    try:
        task = ops.get_task(connection, task_id)
    except ops.TaskNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        ) from None

    return templates.TemplateResponse(
        request=request,
        name="task_form.html",
        context={"task": task},
    )


@router.post("/tasks/{task_id}/edit")
def edit_task(
    task_id: int,
    connection: database_connection,
    name: Annotated[str, Form()],
    priority: Annotated[int, Form()],
    duration: Annotated[int, Form()],
    due_date: Annotated[str, Form()] = "",
):
    try:
        parsed_due_date = date.fromisoformat(due_date) if due_date else None
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Invalid due date",
        ) from None

    try:
        with connection:
            ops.get_task(connection, task_id)

            changes = {
                "name": name,
                "priority": priority,
                "duration": duration,
                "due_date": parsed_due_date,
            }

            for field, value in changes.items():
                ops.edit_task(connection, task_id, field, value)

            scheduler.schedule_tasks(connection)

    except ops.TaskNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        ) from None

    except (ValueError, TypeError) as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    return RedirectResponse(
        url="/web/",
        status_code=303,
    )


@router.post("/tasks/{task_id}/delete")
def delete_task(task_id: int, connection: database_connection):
    with connection:
        deleted = ops.delete_task(connection, task_id)

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Task {task_id} not found",
            )

        scheduler.schedule_tasks(connection)

    return RedirectResponse(
        url="/web/",
        status_code=303,
    )
