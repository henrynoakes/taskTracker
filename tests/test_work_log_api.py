import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime, timedelta

import pytest

from tasktracker import db_connection, scheduler
from tasktracker import database as db

TODAY = date(2026, 7, 2)


def create(client, name, duration, priority=1):
    response = client.post("/tasks", json={"name": name, "duration": duration, "priority": priority})
    assert response.status_code == 201
    return response.json()


@pytest.fixture(autouse=True)
def uk_midnight(freeze_time):
    freeze_time(datetime(2026, 7, 1, 23, 30, tzinfo=UTC))


def test_completion_endpoints_and_summary(client):
    first = create(client, "Maths", 2)
    second = create(client, "Programming", 1)
    assert client.get("/work-log").json() == []
    assert client.get("/work-log/summary").json() == []
    for task in [first, first, second, second]:
        response = client.post(f"/tasks/{task['id']}/complete")
        assert response.status_code == 200
        assert response.json()["completed"] is True
    entries = client.get("/work-log").json()
    assert len(entries) == 2
    assert [(e["task_id"], e["task_name"], e["duration"]) for e in entries] == [
        (first["id"], "Maths", 2), (second["id"], "Programming", 1),
    ]
    assert all(e["work_date"] == TODAY.isoformat() for e in entries)
    assert all(datetime.fromisoformat(e["recorded_at"]).utcoffset() == timedelta(0) for e in entries)
    assert client.get("/work-log", params={"work_date": TODAY.isoformat()}).json() == entries
    assert client.get("/work-log?work_date=2026-07-01").json() == []
    assert client.get("/work-log?work_date=invalid").status_code == 422
    assert client.get("/work-log/summary").json() == [{"date": TODAY.isoformat(), "duration": 3}]
    response = client.post("/tasks/999/complete")
    assert response.status_code == 404
    assert response.json() == {"detail": "Task 999 not found"}
    assert client.get("/work-log").json() == entries


def test_api_history_survives_edits_and_deletion(client):
    task = create(client, "Original", 3)
    url = f"/tasks/{task['id']}"
    assert client.post(f"{url}/complete").status_code == 200
    entry = client.get("/work-log").json()[0]
    assert client.patch(url, json={"name": "Renamed", "duration": 8}).status_code == 200
    assert client.get("/work-log").json() == [entry]
    assert client.delete(url).status_code == 204
    assert client.get("/work-log").json() == [entry | {"task_id": None}]
    assert client.get("/work-log/summary").json() == [{"date": TODAY.isoformat(), "duration": 3}]


def test_automatic_schedule_after_create_edit_and_delete(client):
    first = create(client, "First", 5, priority=1)
    second = create(client, "Second", 5, priority=5)
    assert first["scheduled_date"] == TODAY.isoformat()
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    assert second["scheduled_date"] == tomorrow
    response = client.patch(f"/tasks/{first['id']}", json={"duration": 6})
    assert response.status_code == 200
    assert response.json()["scheduled_date"] is None
    assert client.get(f"/tasks/{second['id']}").json()["scheduled_date"] == TODAY.isoformat()
    assert client.patch(f"/tasks/{first['id']}", json={"duration": 5}).status_code == 200
    assert client.get(f"/tasks/{second['id']}").json()["scheduled_date"] == tomorrow
    assert client.delete(f"/tasks/{first['id']}").status_code == 204
    assert client.get(f"/tasks/{second['id']}").json()["scheduled_date"] == TODAY.isoformat()


def test_completion_does_not_reschedule_and_next_schedule_counts_work(client, monkeypatch):
    first = create(client, "Today", 5)
    second = create(client, "Tomorrow", 3)
    before = client.get("/tasks").json()
    original_schedule = scheduler.schedule_tasks

    def unexpected_schedule(connection):
        pytest.fail("Completion must not invoke the scheduler")

    monkeypatch.setattr(scheduler, "schedule_tasks", unexpected_schedule)
    assert client.post(f"/tasks/{first['id']}/complete").status_code == 200
    assert client.get("/tasks").json() == [before[0] | {"completed": True}, before[1]]
    monkeypatch.setattr(scheduler, "schedule_tasks", original_schedule)
    assert client.post("/schedule").json() == {"all_scheduled": True}
    assert client.get(f"/tasks/{second['id']}").json()["scheduled_date"] == (TODAY + timedelta(days=1)).isoformat()
    # Creation also uses today's work log and never fills today's consumed capacity.
    third = create(client, "New", 2)
    assert third["scheduled_date"] == (TODAY + timedelta(days=1)).isoformat()
    # Removing the original task must not free its historical work capacity.
    assert client.delete(f"/tasks/{first['id']}").status_code == 204
    assert all(t["scheduled_date"] != TODAY.isoformat() for t in client.get("/tasks").json())


def test_manual_schedule_persists_and_reports_unscheduled(client):
    task = create(client, "Fits", 2)
    oversized = create(client, "Too large", 6)
    with closing(db.connect_database(db_connection.database_path)) as connection, connection:
        db.edit_task(connection, task["id"], "scheduled_date", None)
        db.edit_task(connection, oversized["id"], "scheduled_date", "2020-01-01")
    response = client.post("/schedule")
    assert response.status_code == 200
    assert response.json() == {"all_scheduled": False}
    assert client.get(f"/tasks/{task['id']}").json()["scheduled_date"] == TODAY.isoformat()
    assert client.get(f"/tasks/{oversized['id']}").json()["scheduled_date"] is None


@pytest.mark.parametrize("action", ["create", "edit", "delete", "schedule"])
def test_schedule_failure_rolls_back_modification_and_all_schedule_changes(client, action):
    first = create(client, "First", 2)
    second = create(client, "Second", 2)
    completed = create(client, "Completed", 1)
    assert client.post(f"/tasks/{completed['id']}/complete").status_code == 200
    with closing(db.connect_database(db_connection.database_path)) as connection, connection:
        for task in (first, second):
            db.edit_task(connection, task["id"], "scheduled_date", "2020-01-01")
        connection.execute(
            "CREATE TRIGGER fail_schedule BEFORE UPDATE OF scheduled_date ON tasks "
            f"WHEN NEW.id = {second['id']} "
            "BEGIN SELECT RAISE(ABORT, 'schedule failed'); END"
        )
    before = client.get("/tasks").json()
    history = client.get("/work-log").json()
    with pytest.raises(sqlite3.IntegrityError, match="schedule failed"):
        if action == "create":
            client.post("/tasks", json={"name": "Temporary", "priority": 1, "duration": 2})
        elif action == "edit":
            client.patch(f"/tasks/{first['id']}", json={"name": "Temporary"})
        elif action == "delete":
            client.delete(f"/tasks/{completed['id']}")
        else:
            client.post("/schedule")
    assert client.get("/tasks").json() == before
    assert client.get("/work-log").json() == history


def test_failed_patch_rolls_back_earlier_fields(client):
    task = create(client, "Original", 2)
    response = client.patch(f"/tasks/{task['id']}", json={"name": "Temporary", "duration": None})
    assert response.status_code == 422
    assert client.get(f"/tasks/{task['id']}").json() == task


def test_filters_remain_supported(client):
    first = create(client, "First", 2)
    second = create(client, "Second", 6)
    assert client.post(f"/tasks/{first['id']}/complete").status_code == 200
    first = client.get(f"/tasks/{first['id']}").json()
    for field, value, expected in [
        ("completed", "true", [first]), ("completed", "false", [second]),
        ("scheduled_date", TODAY.isoformat(), [first]),
        ("scheduled_date", "null", [second]), ("duration", "6", [second]),
        ("name", "First", [first]), ("id", str(first["id"]), [first]),
    ]:
        response = client.get("/tasks", params={"field": field, "value": value})
        assert response.status_code == 200
        assert response.json() == expected
    for params in [
        {"value": "1"}, {"field": "name"}, {"field": "unknown", "value": "1"},
        {"field": "completed", "value": "maybe"}, {"field": "duration", "value": "invalid"},
        {"field": "scheduled_date", "value": "invalid"},
    ]:
        assert client.get("/tasks", params=params).status_code == 422
