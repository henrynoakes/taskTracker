from datetime import UTC, date, datetime

from tasktracker.models import Task


def test_task_defaults() -> None:
    before = datetime.now(UTC)

    task = Task(id=1, name="Maths", priority=1, duration=3)

    after = datetime.now(UTC)
    assert task.id == 1
    assert task.name == "Maths"
    assert task.priority == 1
    assert task.duration == 3
    assert task.due_date is None
    assert task.completed is False
    assert task.created_at.tzinfo is UTC
    assert before <= task.created_at <= after


def test_task_accepts_explicit_optional_fields() -> None:
    created_at = datetime(2026, 10, 1, 12, tzinfo=UTC)
    due_date = date(2026, 11, 10)

    task = Task(
        id=2,
        name="Physics",
        priority=2,
        duration=4,
        due_date=due_date,
        created_at=created_at,
        completed=True,
    )

    assert task.due_date == due_date
    assert task.created_at == created_at
    assert task.completed is True
