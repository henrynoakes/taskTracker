from collections.abc import Callable
from datetime import date, datetime

import pytest

from tasktracker.validation import (
    validate_completed,
    validate_due_date,
    validate_duration,
    validate_fields,
    validate_name,
    validate_priority,
)


@pytest.mark.parametrize("priority", [0, 6, -1])
def test_invalid_priority(priority: int) -> None:
    with pytest.raises(ValueError):
        validate_priority(priority)


@pytest.mark.parametrize("name", ["Maths", " Physics ", "日本語"])
def test_valid_name(name: str) -> None:
    assert validate_name(name) is None


@pytest.mark.parametrize("name", ["", " ", "\t\n"])
def test_blank_name(name: str) -> None:
    with pytest.raises(ValueError, match="Name cannot be empty"):
        validate_name(name)


@pytest.mark.parametrize("name", [None, 1, True, [], b"Maths"])
def test_name_requires_string(name: object) -> None:
    with pytest.raises(TypeError, match="Name must be a string"):
        validate_name(name)


@pytest.mark.parametrize("completed", [True, False])
def test_valid_completed(completed: bool) -> None:
    assert validate_completed(completed) is None


@pytest.mark.parametrize("completed", [None, 0, 1, "True", []])
def test_completed_requires_boolean(completed: object) -> None:
    with pytest.raises(TypeError, match="Completed must be a boolean"):
        validate_completed(completed)


@pytest.mark.parametrize("duration", range(1, 11))
def test_valid_duration(duration: int) -> None:
    assert validate_duration(duration) is None


@pytest.mark.parametrize("duration", [-1, 0, 11])
def test_invalid_duration(duration: int) -> None:
    with pytest.raises(ValueError, match="Duration must be between 1 and 10 blocks"):
        validate_duration(duration)


@pytest.mark.parametrize("priority", range(1, 6))
def test_valid_priority(priority: int) -> None:
    assert validate_priority(priority) is None


@pytest.mark.parametrize(
    "validator, message",
    [
        (validate_duration, "Duration must be an integer"),
        (validate_priority, "Priority must be an integer"),
    ],
)
@pytest.mark.parametrize("value", [None, True, False, 1.0, "1", []])
def test_numeric_fields_require_integer(
    validator: Callable[[object], None],
    message: str,
    value: object,
) -> None:
    with pytest.raises(TypeError, match=message):
        validator(value)


@pytest.mark.parametrize("due_date", [None, date(2000, 1, 1), date(2099, 12, 31)])
def test_valid_due_date(due_date: date | None) -> None:
    assert validate_due_date(due_date) is None


@pytest.mark.parametrize(
    "due_date", ["2026-11-10", datetime(2026, 11, 10), 1, True, []]
)
def test_due_date_requires_date_or_none(due_date: object) -> None:
    with pytest.raises(TypeError, match="Due date must be a date object or None"):
        validate_due_date(due_date)


@pytest.mark.parametrize("field", ["name", "completed", "duration", "priority", "due_date"])
def test_editable_fields(field: str) -> None:
    assert validate_fields(field) is None


@pytest.mark.parametrize("field", ["id", "created_at", "unknown", "", None])
def test_unknown_field(field: object) -> None:
    with pytest.raises(ValueError, match="Unknown field:"):
        validate_fields(field)
