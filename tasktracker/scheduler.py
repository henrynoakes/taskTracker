import sqlite3
from datetime import date, datetime, timedelta

from . import operations as ops
from .models import Task


def calculate_importance(task: Task, today: date) -> float:
    # Priority: 0 to 5
    priority_score = 5 * (5 - task.priority) / 4

    # Age: 0 to 2
    age_days = max(0, (today - task.created_at.date()).days)
    age_score = 2 * min(age_days / 30, 1)

    # Deadline urgency: 0 to 8
    if task.due_date is None:
        urgency_score = 0.0
    else:
        days_left = (task.due_date - today).days
        urgency_score = 8 / (max(days_left, 0) + 1)

    # Duration: 0.05 to 0.5, a small preference for longer tasks.
    duration_score = 0.05 * task.duration

    return priority_score + age_score + urgency_score + duration_score


def calculate_schedule(
    tasks: list[Task],
    today: date,
    daily_capacity: int = 5,
    completed_today: int = 0,
) -> dict[int, date]:
    if daily_capacity <= 0:
        raise ValueError("Daily capacity must be positive")
    if completed_today < 0:
        raise ValueError("Completed work must not be negative")

    remaining_tasks = sorted(
        tasks,
        key=lambda task: (
            -calculate_importance(task, today),
            task.id,
        ),
    )

    assignments: dict[int, date] = {}
    current_day = today

    while remaining_tasks:
        remaining_capacity = daily_capacity
        if current_day == today:
            remaining_capacity = max(0, daily_capacity - completed_today)
        scheduled_any = False

        while True:
            for task in remaining_tasks:
                if task.duration <= remaining_capacity:
                    assignments[task.id] = current_day
                    remaining_capacity -= task.duration
                    remaining_tasks.remove(task)
                    scheduled_any = True
                    break
            else:
                break

        if not scheduled_any and (current_day != today or completed_today == 0):
            # No task fits into an empty day.
            break

        current_day += timedelta(days=1)

    return assignments


def schedule_tasks(database: sqlite3.Connection) -> bool:
    """Persist the schedule without committing; the caller owns the transaction."""
    today = datetime.now(ops.UK_TIMEZONE).date()
    tasks = ops.list_tasks(database, "completed", False)

    completed_today = ops.get_work_duration(database, today)
    assignments = calculate_schedule(tasks, today, completed_today=completed_today)

    for task in tasks:
        ops.edit_task(
            database,
            task.id,
            "scheduled_date",
            assignments.get(task.id),
        )

    return len(assignments) == len(tasks)
