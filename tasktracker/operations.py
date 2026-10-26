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


class TaskNotFoundError(LookupError):
    pass


def add_task(
    task_list: list[Task],
    name: str,
    priority: int,
    duration: int,
    due_date: date | None = None,
) -> None:
    # validation step
    validate_name(name)
    validate_priority(priority)
    validate_duration(duration)
    validate_due_date(due_date)

    task = Task(
        id=len(task_list) + 1,
        name=name,
        due_date=due_date,
        priority=priority,
        duration=duration,
    )

    task_list.append(task)


def find_task(
    task_list: list[Task], task_id: int
) -> (
    Task | None
):  # For when the task doesn't need to exist. If it doesn't it just returns None, which can be useful.
    for task in task_list:
        if task.id == task_id:
            return task
    return None


def get_task(
    task_list: list[Task], task_id: int
) -> Task:  # For when the task needs to exist. If it doesn't it causes an error.
    task = find_task(task_list, task_id)
    if task is None:
        raise TaskNotFoundError(f"Task with id {task_id} was not found")
    return task


def complete_task(task_list: list[Task], task_id: int) -> bool:
    task = find_task(task_list, task_id)
    if task is not None:
        task.completed = True
        return True
    return False


def delete_task(task_list: list[Task], task_id: int) -> bool:
    task = find_task(task_list, task_id)
    if task is not None:
        task_list.remove(task)
        return True
    return False


def edit_task(task_list: list[Task], task_id: int, field: str, value: object) -> bool:
    # Validation step
    validate_fields(field)
    validators[field](value)

    task = find_task(task_list, task_id)
    if task is not None:
        setattr(task, field, value)
        return True
    return False
