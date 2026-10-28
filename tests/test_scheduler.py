from collections import Counter
from datetime import UTC, date, datetime, timedelta

import pytest

from tasktracker import database as db
from tasktracker import operations as ops
from tasktracker import scheduler
from tasktracker.models import Task

TODAY = date(2026, 7, 2)


def make_task(task_id, duration, priority=1):
    return Task(task_id, f"Task {task_id}", priority, duration, datetime(2026, 7, 1, tzinfo=UTC))


@pytest.mark.parametrize(
    "completed, durations, offsets",
    [
        (3, [2, 3, 2], [0, 1, 1]),
        (5, [2, 2, 2], [1, 1, 2]),
        (3, [3, 3], [1, 2]),
        (8, [5, 5], [1, 2]),
        (0, [6], [None]),
        (5, [6], [None]),
        (3, [6, 2, 3], [None, 0, 1]),
        (0, [], []),
    ],
)
def test_schedule_accounts_for_work_and_oversized_tasks(completed, durations, offsets):
    tasks = [make_task(i, duration) for i, duration in enumerate(durations, 1)]
    assignments = scheduler.calculate_schedule(tasks, TODAY, completed_today=completed)
    assert assignments == {
        task.id: TODAY + timedelta(days=offset)
        for task, offset in zip(tasks, offsets) if offset is not None
    }


@pytest.mark.parametrize("completed", [0, 1, 3, 5, 8])
def test_schedule_capacity_and_priority_order(completed):
    tasks = [make_task(i, duration, priority=(i % 5) + 1)
             for i, duration in enumerate([1, 3, 2, 5, 6, 4, 1, 10], 1)]
    assignments = scheduler.calculate_schedule(tasks, TODAY, completed_today=completed)
    totals = Counter()
    for task in tasks:
        if task.id in assignments:
            totals[assignments[task.id]] += task.duration
        else:
            assert task.duration > 5
    assert totals[TODAY] <= max(0, 5 - completed)
    assert all(duration <= 5 for day, duration in totals.items() if day != TODAY)
    # Same importance: ID breaks the tie, regardless of input order.
    assert scheduler.calculate_schedule([make_task(2, 5), make_task(1, 5)], TODAY) == {
        1: TODAY, 2: TODAY + timedelta(days=1),
    }


def test_importance_formula_unchanged():
    task = make_task(1, 3, priority=3)
    task.created_at = datetime(2026, 6, 17, tzinfo=UTC)
    task.due_date = TODAY + timedelta(days=3)
    assert scheduler.calculate_importance(task, TODAY) == 2.5 + 1 + 2


@pytest.mark.parametrize("capacity, completed", [(0, 0), (-1, 0), (5, -1)])
def test_invalid_capacity(capacity, completed):
    with pytest.raises(ValueError):
        scheduler.calculate_schedule([], TODAY, capacity, completed)


def test_persist_schedule_uses_uk_date_and_logged_duration(connection, freeze_time):
    freeze_time(datetime(2026, 7, 1, 23, 30, tzinfo=UTC))
    with connection:
        completed = ops.add_task(connection, "Done", 1, 3, scheduled_date=TODAY)
        ops.complete_task(connection, completed)
        # Current task estimates must not affect historical capacity.
        ops.edit_task(connection, completed, "duration", 10)
        small = ops.add_task(connection, "Small", 1, 2)
        normal = ops.add_task(connection, "Normal", 1, 5)
        oversized = ops.add_task(connection, "Too large", 1, 6, scheduled_date=TODAY)
        db.insert_work_log(connection, None, "Yesterday", TODAY - timedelta(days=1),
                           datetime(2026, 7, 1, 12, tzinfo=UTC), 5)
        assert scheduler.schedule_tasks(connection) is False
    assert ops.get_task(connection, completed).scheduled_date == TODAY
    assert ops.get_task(connection, small).scheduled_date == TODAY
    assert ops.get_task(connection, normal).scheduled_date == TODAY + timedelta(days=1)
    assert ops.get_task(connection, oversized).scheduled_date is None
    with connection:
        ops.delete_task(connection, completed)
        ops.delete_task(connection, oversized)
        assert scheduler.schedule_tasks(connection) is True
    assert ops.get_task(connection, small).scheduled_date == TODAY
    assert ops.get_task(connection, normal).scheduled_date == TODAY + timedelta(days=1)


def test_schedule_does_not_commit(connection, freeze_time):
    freeze_time(datetime(2026, 7, 2, 12, tzinfo=UTC))
    with connection:
        task_id = ops.add_task(connection, "Original", 1, 3)
    with pytest.raises(RuntimeError), connection:
        ops.edit_task(connection, task_id, "name", "Temporary")
        assert scheduler.schedule_tasks(connection)
        assert ops.get_task(connection, task_id).scheduled_date == TODAY
        raise RuntimeError("Failure after scheduling")
    task = ops.get_task(connection, task_id)
    assert task.name == "Original"
    assert task.scheduled_date is None
