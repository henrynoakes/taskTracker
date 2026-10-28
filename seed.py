from datetime import date, datetime, timedelta, UTC

from tasktracker import database as db

DATABASE_PATH = "tasks.db"

today = date.today()

# (name, priority, duration, days_until_due, age_in_days)
# None for days_until_due means no deadline.
tasks = [
    ("Complete maths assignment", 1, 4, 1, 2),
    ("Read C textbook", 3, 2, None, 20),
    ("Finish robotics report", 1, 5, 0, 5),
    ("Review lecture notes", 2, 2, 3, 1),
    ("Organise university files", 5, 1, None, 45),
    ("Complete programming exercise", 2, 3, 2, 7),
    ("Study electrical engineering", 2, 4, 5, 3),
    ("Read research paper", 4, 2, None, 30),
    ("Prepare presentation", 1, 5, 7, 10),
    ("Revise calculus", 3, 3, 4, 14),
    ("Update project documentation", 4, 2, None, 40),
    ("Submit lab worksheet", 2, 3, -1, 12),
    ("Fix Python bugs", 1, 2, None, 15),
    ("Complete mechanics problems", 3, 4, 10, 5),
    ("Review old flashcards", 5, 1, None, 60),
    ("Write project proposal", 2, 5, -3, 20),
    ("Practise C programming", 3, 2, None, 2),
    ("Finish overdue assignment", 1, 4, -7, 25),
    ("Research motor controllers", 4, 3, 14, 8),
    ("Clean up Git repositories", 5, 1, None, 35),
]

connection = db.connect_database(DATABASE_PATH)
db.initialize_database(connection)

with connection:
    connection.execute("DELETE FROM tasks")

    for name, priority, duration, days_until_due, age_in_days in tasks:
        due_date = (
            (today + timedelta(days=days_until_due)).isoformat()
            if days_until_due is not None
            else None
        )

        created_at = (datetime.now(UTC) - timedelta(days=age_in_days)).isoformat()

        connection.execute(
            """
            INSERT INTO tasks
                (name, priority, duration, due_date, created_at, completed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (name, priority, duration, due_date, created_at),
        )

connection.close()

print(f"Seeded {len(tasks)} tasks.")
