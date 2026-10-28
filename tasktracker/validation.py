from collections.abc import Callable
from datetime import date


def validate_name(name: object) -> None:
    if not isinstance(name, str):
        raise TypeError("Name must be a string")

    if not name.strip():
        raise ValueError("Name cannot be empty")


def validate_completed(completed: object) -> None:
    if type(completed) is not bool:
        raise TypeError("Completed must be a boolean")


def validate_duration(duration: object) -> None:
    if type(duration) is not int:
        raise TypeError("Duration must be an integer")

    if duration <= 0 or duration > 10:
        raise ValueError("Duration must be between 1 and 10 blocks")


def validate_priority(priority: object) -> None:
    if type(priority) is not int:
        raise TypeError("Priority must be an integer")

    if (
        priority < 1 or priority > 5
    ):  # Possibly make this defined in config so that it is the same as pydantic
        raise ValueError("Priority must be between 1 and 5")


def validate_due_date(due_date: object) -> None:
    if due_date is None:
        return

    if type(due_date) is not date:
        raise TypeError("Due date must be a date object or None")


def validate_scheduled_date(scheduled_date: object) -> None:
    if scheduled_date is None:
        return

    if type(scheduled_date) is not date:
        raise TypeError("Scheduled date must be a date object or None")


def validate_fields(field: object) -> None:
    if field not in validators:
        raise ValueError(f"Unknown field: {field}")


validators: dict[
    str, Callable[[object], None]
] = {  # Dispatch table to be called when editing a task, makes it easier to select which validation function should be used, as opposed to a series of if statements
    "name": validate_name,
    "duration": validate_duration,
    "priority": validate_priority,
    "due_date": validate_due_date,
    "scheduled_date": validate_scheduled_date,
}
