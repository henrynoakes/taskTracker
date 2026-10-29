from datetime import date, datetime
from itertools import groupby
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import operations as ops
from . import scheduler
from .db_connection import database_connection
from .markdown_rendering import render_markdown, render_markdown_preview
from .web_formatting import format_duration, format_schedule_date

router = APIRouter(prefix="/web")

templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
templates.env.filters["markdown"] = render_markdown
templates.env.filters["markdown_preview"] = render_markdown_preview


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
    description: Annotated[str | None, Form()] = None,
):
    parsed_due_date = date.fromisoformat(due_date) if due_date else None

    with connection:
        ops.add_task(
            connection,
            name=name,
            priority=priority,
            duration=duration,
            due_date=parsed_due_date,
            description=description,
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
def regenerate_schedule(
    connection: database_connection,
    return_to: Annotated[str, Form()] = "/web/",
):
    with connection:
        scheduler.schedule_tasks(connection)

    return RedirectResponse(
        url=return_to if return_to in {"/web/", "/web/schedule"} else "/web/",
        status_code=303,
    )


@router.get("/schedule", response_class=HTMLResponse)
def schedule(request: Request, connection: database_connection):
    today = datetime.now(ops.UK_TIMEZONE).date()
    tasks = ops.list_tasks(
        connection, field="completed", value=False, sort_by="scheduled_date",
    )
    groups = []
    for scheduled_date, task_group in groupby(tasks, key=lambda task: task.scheduled_date):
        grouped_tasks = list(task_group)
        groups.append({
            "heading": format_schedule_date(scheduled_date, today)
            if scheduled_date is not None else "Unscheduled",
            "overdue": scheduled_date is not None and scheduled_date < today,
            "tasks": grouped_tasks,
            "duration": format_duration(sum(task.duration for task in grouped_tasks)),
        })

    return templates.TemplateResponse(
        request=request,
        name="schedule.html",
        context={"groups": groups},
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
    description: Annotated[str | None, Form()] = None,
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
                "description": description,
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


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(request: Request, task_id: int, connection: database_connection):
    try:
        task = ops.get_task(connection, task_id)
    except ops.TaskNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        ) from None

    return templates.TemplateResponse(
        request=request,
        name="task_detail.html",
        context={"task": task},
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
