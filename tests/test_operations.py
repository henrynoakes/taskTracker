from collections.abc import Callable
from copy import deepcopy
from datetime import date
from typing import Any

import pytest

from tasktracker.models import Task
from tasktracker.operations import (
    TaskNotFoundError,
    add_task,
    complete_task,
    delete_task,
    edit_task,
    find_task,
    get_task,
)


@pytest.fixture
def tasks() -> list[Task]:
    return [
        Task(id=1, name="Maths", priority=1, duration=3),
        Task(id=2, name="Physics", priority=2, duration=4, due_date=date(2026, 11, 10)),
    ]


def test_add_task() -> None:
    tasks: list[Task] = []

    add_task(tasks, "Maths", 1, 3)

    assert len(tasks) == 1
    assert tasks[0].name == "Maths"
    assert tasks[0].priority == 1
    assert tasks[0].duration == 3
    assert tasks[0].completed is False


def test_add_task_with_due_date(tasks: list[Task]) -> None:
    due_date = date(2026, 12, 1)

    add_task(tasks, "Chemistry", 5, 10, due_date=due_date)

    assert len(tasks) == 3
    assert tasks[-1].id == 3
    assert tasks[-1].name == "Chemistry"
    assert tasks[-1].priority == 5
    assert tasks[-1].duration == 10
    assert tasks[-1].due_date == due_date


@pytest.mark.parametrize(
    "field, value, error",
    [
        ("name", " ", ValueError),
        ("name", None, TypeError),
        ("priority", 6, ValueError),
        ("priority", True, TypeError),
        ("duration", 0, ValueError),
        ("duration", 1.5, TypeError),
        ("due_date", "2026-11-10", TypeError),
    ],
)
def test_invalid_add_leaves_tasks_unchanged(
    tasks: list[Task],
    field: str,
    value: object,
    error: type[Exception],
) -> None:
    original = deepcopy(tasks)
    values: dict[str, Any] = dict(name="Chemistry", priority=3, duration=2, due_date=None)
    values[field] = value

    with pytest.raises(error):
        add_task(tasks, **values)

    assert tasks == original


@pytest.mark.parametrize("lookup", [find_task, get_task])
def test_lookup_returns_existing_task(
    tasks: list[Task],
    lookup: Callable[[list[Task], int], Task | None],
) -> None:
    assert lookup(tasks, 2) is tasks[1]


@pytest.mark.parametrize("task_id", [0, 3])
def test_find_missing_task(tasks: list[Task], task_id: int) -> None:
    assert find_task(tasks, task_id) is None


def test_get_missing_task(tasks: list[Task]) -> None:
    with pytest.raises(TaskNotFoundError, match="Task with id 3 was not found"):
        get_task(tasks, 3)


def test_complete_task(tasks: list[Task]) -> None:
    original_other = deepcopy(tasks[1])

    assert complete_task(tasks, 1) is True
    assert tasks[0].completed is True
    assert tasks[1] == original_other


def test_complete_already_completed_task(tasks: list[Task]) -> None:
    tasks[0].completed = True

    assert complete_task(tasks, 1) is True
    assert tasks[0].completed is True


def test_delete_task(tasks: list[Task]) -> None:
    remaining = tasks[1]

    assert delete_task(tasks, 1) is True
    assert tasks == [remaining]
    assert remaining.id == 2
    assert find_task(tasks, 1) is None


@pytest.mark.parametrize("operation", [complete_task, delete_task])
def test_missing_task_leaves_list_unchanged(
    tasks: list[Task],
    operation: Callable[[list[Task], int], bool],
) -> None:
    original = deepcopy(tasks)

    assert operation(tasks, 3) is False
    assert tasks == original


@pytest.mark.parametrize(
    "field, value",
    [
        ("name", "Algebra"),
        ("priority", 5),
        ("duration", 10),
        ("due_date", date(2026, 12, 1)),
        ("due_date", None),
        ("completed", True),
        ("completed", False),
    ],
)
def test_edit_task_changes_only_requested_field(
    tasks: list[Task],
    field: str,
    value: object,
) -> None:
    expected = deepcopy(tasks)
    setattr(expected[1], field, value)

    assert edit_task(tasks, 2, field, value) is True
    assert tasks == expected


@pytest.mark.parametrize(
    "field, value, error",
    [
        ("name", "", ValueError),
        ("name", None, TypeError),
        ("priority", 0, ValueError),
        ("priority", True, TypeError),
        ("duration", 11, ValueError),
        ("duration", "2", TypeError),
        ("due_date", "2026-11-10", TypeError),
        ("completed", 1, TypeError),
        ("id", 10, ValueError),
        ("created_at", None, ValueError),
    ],
)
def test_invalid_edit_leaves_tasks_unchanged(
    tasks: list[Task],
    field: str,
    value: object,
    error: type[Exception],
) -> None:
    original = deepcopy(tasks)

    with pytest.raises(error):
        edit_task(tasks, 1, field, value)

    assert tasks == original


def test_edit_missing_task(tasks: list[Task]) -> None:
    original = deepcopy(tasks)

    assert edit_task(tasks, 3, "name", "Chemistry") is False
    assert tasks == original


def test_edit_validates_before_looking_up_task(tasks: list[Task]) -> None:
    with pytest.raises(ValueError, match="Priority must be between 1 and 5"):
        edit_task(tasks, 3, "priority", 0)


def test_operations_on_empty_list() -> None:
    tasks: list[Task] = []

    assert find_task(tasks, 1) is None
    with pytest.raises(TaskNotFoundError):
        get_task(tasks, 1)
    assert complete_task(tasks, 1) is False
    assert delete_task(tasks, 1) is False
    assert edit_task(tasks, 1, "name", "Maths") is False
    assert tasks == []
