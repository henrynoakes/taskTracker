from datetime import date


def validate_name(name):
    if not isinstance(name, str):
        raise TypeError("Name must be a string")

    if not name.strip():
        raise ValueError("Name cannot be empty")


def validate_completed(completed):
    if type(completed) is not bool:
        raise TypeError("Completed must be a boolean")


def validate_duration(duration):
    if type(duration) is not int:
        raise TypeError("Duration must be an integer")

    if duration <= 0 or duration > 10:
        raise ValueError("Duration must be between 1 and 10 blocks")


def validate_priority(priority):
    if type(priority) is not int:
        raise TypeError("Priority must be an integer")

    if priority < 1 or priority > 5:
        raise ValueError("Priority must be between 1 and 5")


def validate_due_date(due_date):
    if due_date is None:
        return

    if type(due_date) is not date:
        raise TypeError("Due date must be a date object or None")


def validate_fields(field):
    if field not in validators:
        raise ValueError(f"Unknown field: {field}")


validators = {  # Dispatch table
    "name": validate_name,
    "completed": validate_completed,
    "duration": validate_duration,
    "priority": validate_priority,
    "due_date": validate_due_date,
}
