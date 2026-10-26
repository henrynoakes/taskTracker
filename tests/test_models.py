from datetime import UTC, date, datetime

import pytest

from tasktracker.models import Task


def test_task_defaults() -> None:
    created_at = datetime(2026, 10, 1, 12, tzinfo=UTC)
    task = Task(id=1, name="Maths", priority=1, duration=3, created_at=created_at)

    assert task.id == 1
    assert task.name == "Maths"
    assert task.priority == 1
    assert task.duration == 3
    assert task.created_at == created_at
    assert task.due_date is None
    assert task.completed is False


def test_task_accepts_explicit_optional_fields() -> None:
    created_at = datetime(2026, 10, 1, 12, tzinfo=UTC)
    due_date = date(2026, 11, 10)
    task = Task(
        id=2, name="Physics", priority=2, duration=4,
        created_at=created_at, due_date=due_date, completed=True,
    )

    assert task.created_at == created_at
    assert task.due_date == due_date
    assert task.completed is True


def test_created_at_is_required() -> None:
    with pytest.raises(TypeError, match="created_at"):
        Task(id=1, name="Maths", priority=1, duration=3)
