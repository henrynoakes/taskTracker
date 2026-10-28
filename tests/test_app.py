import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tasktracker import db_connection, scheduler
from tasktracker import database as db
from tasktracker import operations as ops
from tasktracker.app import app


def test_api_and_web_routes_registered(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {path: set(methods) for path, methods in paths.items()} == {
        "/": {"get"},
        "/tasks": {"get", "post"},
        "/tasks/{task_id}": {"get", "patch", "delete"},
        "/tasks/{task_id}/complete": {"post"},
        "/schedule": {"post"},
        "/work-log": {"get"},
        "/work-log/summary": {"get"},
        "/web/": {"get"},
        "/web/tasks/new": {"get", "post"},
        "/web/tasks/{task_id}/edit": {"get", "post"},
        "/web/tasks/{task_id}/complete": {"post"},
        "/web/tasks/{task_id}/delete": {"post"},
        "/web/schedule": {"post"},
    }


def test_static_files_served(client):
    response = client.get("/static/style.css")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    stylesheet = Path(__file__).resolve().parent.parent / "tasktracker/static/style.css"
    assert response.content == stylesheet.read_bytes()


def test_startup_initializes_new_and_existing_database(tmp_path, monkeypatch):
    path = tmp_path / "startup.db"
    monkeypatch.setattr(db_connection, "database_path", path)
    assert not path.exists()
    with TestClient(app) as client:
        assert path.exists()
        assert client.get("/tasks").json() == []
        assert client.get("/work-log").json() == []
        task = client.post("/tasks", json={"name": "Retained", "priority": 1, "duration": 2}).json()
    with TestClient(app) as client:
        assert client.get(f"/tasks/{task['id']}").json() == task
        assert client.get("/work-log").json() == []


@pytest.fixture
def tracked_connections(monkeypatch):
    connections = []
    original_connect = sqlite3.connect

    class TrackedConnection(sqlite3.Connection):
        closed = False

        def close(self):
            super().close()
            self.closed = True

    def connect(*args, **kwargs):
        connection = original_connect(*args, factory=TrackedConnection, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    return connections


@pytest.mark.parametrize("path", ["/tasks", "/tasks/999", "/web/", "/web/tasks/999/edit"])
def test_request_connections_closed(client, tracked_connections, path):
    response = client.get(path)
    assert response.status_code in {200, 404}
    assert len(tracked_connections) == 1
    assert tracked_connections[0].closed


@pytest.mark.parametrize("path", ["/tasks", "/web/"])
def test_connections_closed_when_handler_fails(client, tracked_connections, monkeypatch, path):
    def fail(*args, **kwargs):
        raise RuntimeError("Handler failed")

    monkeypatch.setattr(ops, "list_tasks", fail)
    with pytest.raises(RuntimeError, match="Handler failed"):
        client.get(path)
    assert len(tracked_connections) == 1
    assert tracked_connections[0].closed


@pytest.mark.parametrize("fail_startup", [False, True])
def test_startup_connection_closed(tmp_path, monkeypatch, tracked_connections, fail_startup):
    monkeypatch.setattr(db_connection, "database_path", tmp_path / "startup.db")
    if fail_startup:
        def fail(connection):
            raise RuntimeError("Startup failed")

        monkeypatch.setattr(db, "initialize_database", fail)
        with pytest.raises(RuntimeError, match="Startup failed"), TestClient(app):
            pass
    else:
        with TestClient(app):
            assert len(tracked_connections) == 1
            assert tracked_connections[0].closed
    assert len(tracked_connections) == 1
    assert tracked_connections[0].closed


def test_web_forms_commit_using_shared_database(client):
    assert client.get("/web/tasks/new").status_code == 200
    response = client.post(
        "/web/tasks/new", data={"name": "Web task", "priority": 1, "duration": 2},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/web/"
    task = client.get("/tasks").json()[0]
    task_id = task["id"]
    assert "Web task" in client.get("/web/").text
    assert "Web task" in client.get(f"/web/tasks/{task_id}/edit").text
    response = client.post(
        f"/web/tasks/{task_id}/edit",
        data={"name": "Edited web task", "priority": 2, "duration": 3, "due_date": "2026-11-10"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    updated = client.get(f"/tasks/{task_id}").json()
    assert (updated["name"], updated["priority"], updated["duration"], updated["due_date"]) == (
        "Edited web task", 2, 3, "2026-11-10",
    )
    for _ in range(2):
        assert client.post(f"/web/tasks/{task_id}/complete", follow_redirects=False).status_code == 303
    assert client.get(f"/tasks/{task_id}").json()["completed"] is True
    entries = client.get("/work-log").json()
    assert len(entries) == 1
    assert entries[0]["task_name"] == "Edited web task"
    assert entries[0]["duration"] == 3
    assert client.post("/web/schedule", follow_redirects=False).status_code == 303
    assert client.post(f"/web/tasks/{task_id}/delete", follow_redirects=False).status_code == 303
    assert client.get("/tasks").json() == []
    assert client.get("/work-log").json() == [entries[0] | {"task_id": None}]


@pytest.mark.parametrize("action", ["create", "edit", "delete", "schedule"])
def test_web_transactions_roll_back_when_scheduling_fails(client, monkeypatch, action):
    task = client.post("/tasks", json={"name": "Original", "priority": 1, "duration": 2}).json()
    client.post(f"/tasks/{task['id']}/complete")
    before_tasks = client.get("/tasks").json()
    before_log = client.get("/work-log").json()
    original_schedule = scheduler.schedule_tasks

    def fail(connection):
        original_schedule(connection)
        raise RuntimeError("Schedule failed")

    monkeypatch.setattr(scheduler, "schedule_tasks", fail)
    with pytest.raises(RuntimeError, match="Schedule failed"):
        if action == "create":
            client.post("/web/tasks/new", data={"name": "Temporary", "priority": 1, "duration": 2})
        elif action == "edit":
            client.post(f"/web/tasks/{task['id']}/edit", data={"name": "Temporary", "priority": 1, "duration": 2})
        elif action == "delete":
            client.post(f"/web/tasks/{task['id']}/delete")
        else:
            client.post("/web/schedule")
    assert client.get("/tasks").json() == before_tasks
    assert client.get("/work-log").json() == before_log
