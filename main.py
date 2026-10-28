from tasktracker import database as db
from tasktracker import scheduler


def main() -> None:
    connection = db.connect_database("tasks.db")

    db.initialize_database(connection)

    with connection:
        result = scheduler.schedule_tasks(connection)

    print("All tasks scheduled:", result)

    for task in db.list_tasks(connection):
        print(task.id, task.name, task.scheduled_date)

    connection.close()


if __name__ == "__main__":
    main()
