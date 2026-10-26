from dataclasses import dataclass, field
from datetime import UTC, date, datetime

tasks = []


@dataclass
class Task:
    id: int
    name: str
    priority: int
    duration: int
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    due_date: date | None = None
    completed: bool = False


def add_task(task_list, name, priority, duration, due_date=None):
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
    task_list, task_id
):  # For when the task doesn't need to exist. If it doesn't it just returns None, which can be useful.
    for task_dir in task_list:
        if task_dir.id == task_id:
            return task_dir
    return None


class TaskNotFoundError(LookupError):
    pass


def get_task(
    task_list, task_id
):  # For when the task needs to exist. If it doesn't it causes an error.
    task_dir = find_task(task_list, task_id)
    if task_dir is None:
        raise TaskNotFoundError(f"Task with id {task_id} was not found")
    return task_dir


def complete_task(task_list, task_id):
    task = find_task(task_list, task_id)
    if task is not None:
        task.completed = True
        return True
    return False


def delete_task(task_list, task_id):
    task = find_task(task_list, task_id)
    if task is not None:
        task_list.remove(task)
        return True
    return False


def edit_task(task_list, task_id, field, value):
    # Validation step
    validate_fields(field)
    validators[field](value)

    task = find_task(task_list, task_id)
    if task is not None:
        setattr(task, field, value)
        return True
    return False


### Validation checks
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

add_task(tasks, "Maths", 1, 3)
add_task(tasks, "Physics", 2, 4)

assert len(tasks) == 2
assert get_task(tasks, 1).name == "Maths"

assert complete_task(tasks, 1) is True
assert get_task(tasks, 1).completed is True

assert edit_task(tasks, 2, "priority", 1) is True
assert get_task(tasks, 2).priority == 1

assert delete_task(tasks, 1) is True
assert find_task(tasks, 1) is None
