from datetime import date

from tasktracker.operations import (
    add_task,
    complete_task,
    delete_task,
    edit_task,
    find_task,
    get_task,
)


def main():
    tasks = []

    add_task(tasks, "Maths", 1, 3)

    add_task(
        tasks,
        "Physics",
        2,
        4,
        due_date=date(2026, 11, 10),
    )

    assert get_task(tasks, 1).name == "Maths"
    assert complete_task(tasks, 1) is True
    assert edit_task(tasks, 2, "priority", 1) is True
    assert delete_task(tasks, 1) is True
    assert find_task(tasks, 1) is None

    print(tasks)


if __name__ == "__main__":
    main()
