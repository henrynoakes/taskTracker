from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from tasktracker import operations as ops


@pytest.fixture
def task(client: TestClient) -> dict:
    response = client.post(
        "/tasks",
        json={"name": "Maths", "priority": 2, "duration": 3, "due_date": "2026-11-10"},
    )
    assert response.status_code == 201
    return response.json()


def test_root(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Task tracker API"}


def test_list_tasks_empty(client: TestClient) -> None:
    response = client.get("/tasks")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("due_date", [None, "2026-11-10"])
def test_create_task(client: TestClient, due_date: str | None) -> None:
    payload = {"name": "日本語 homework", "priority": 5, "duration": 10}
    if due_date is not None:
        payload["due_date"] = due_date
    before = datetime.now(UTC)

    response = client.post("/tasks", json=payload)

    after = datetime.now(UTC)
    assert response.status_code == 201
    task = response.json()
    assert type(task["id"]) is int
    created_at = datetime.fromisoformat(task["created_at"])
    assert created_at.utcoffset().total_seconds() == 0
    assert before <= created_at <= after
    assert task == {
        "id": task["id"],
        "name": payload["name"],
        "priority": 5,
        "duration": 10,
        "due_date": due_date,
        "created_at": task["created_at"],
        "completed": False,
        "scheduled_date": None,
        "description": None,
    }
    assert client.get(f"/tasks/{task['id']}").json() == task


def test_get_task(client: TestClient, task: dict) -> None:
    response = client.get(f"/tasks/{task['id']}")

    assert response.status_code == 200
    assert response.json() == task


def test_scheduled_date_edits_are_recalculated(client: TestClient) -> None:
    response = client.post(
        "/tasks", json={"name": "Scheduled", "priority": 2, "duration": 3,
                        "scheduled_date": "2026-11-01"},
    )
    assert response.status_code == 201
    task = response.json()
    assert task["scheduled_date"] == datetime.now(ops.UK_TIMEZONE).date().isoformat()
    assert client.get(f"/tasks/{task['id']}").json() == task
    response = client.patch(f"/tasks/{task['id']}", json={"scheduled_date": None})
    assert response.status_code == 200
    assert response.json() == task


def test_list_tasks(client: TestClient, task: dict) -> None:
    response = client.post(
        "/tasks", json={"name": "Physics", "priority": 1, "duration": 1}
    )
    assert response.status_code == 201
    other = response.json()

    response = client.get("/tasks")

    assert response.status_code == 200
    assert sorted(response.json(), key=lambda item: item["id"]) == [task, other]


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "Chemistry"},
        {"priority": 5},
        {"duration": 10},
        {"due_date": "2026-12-01"},
        {"due_date": None},
        {"scheduled_date": "2026-11-01"},
        {"scheduled_date": None},
        {"name": "Updated", "priority": 1, "duration": 1},
        {},
    ],
)
def test_update_task(client: TestClient, task: dict, changes: dict) -> None:
    other = client.post(
        "/tasks", json={"name": "Physics", "priority": 3, "duration": 4}
    ).json()

    response = client.patch(f"/tasks/{task['id']}", json=changes)

    assert response.status_code == 200
    expected = task | changes
    expected["scheduled_date"] = response.json()["scheduled_date"]
    assert response.json() == expected
    assert client.get(f"/tasks/{task['id']}").json() == expected
    current_other = client.get(f"/tasks/{other['id']}").json()
    assert current_other == other | {"scheduled_date": current_other["scheduled_date"]}


@pytest.mark.parametrize("completed", [True, False, None])
def test_patch_completion_is_rejected(client: TestClient, task: dict, completed) -> None:
    url = f"/tasks/{task['id']}"
    assert client.post(f"{url}/complete").status_code == 200
    before = client.get(url).json()
    response = client.patch(url, json={"completed": completed})
    assert response.status_code == 422
    assert client.get(url).json() == before


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": "Maths", "priority": 1},
        {"name": "Maths", "duration": 1},
        {"priority": 1, "duration": 1},
        *[
            {"name": "Maths", "priority": 1, "duration": 1} | {field: value}
            for field, value in [
                ("name", ""), ("name", "   "), ("name", None), ("name", 123),
                ("priority", 0), ("priority", 6), ("priority", None),
                ("duration", 0), ("duration", 11), ("duration", 1.5),
                ("due_date", "not-a-date"), ("scheduled_date", "not-a-date"),
            ]
        ],
    ],
)
def test_invalid_create_leaves_tasks_unchanged(
    client: TestClient, task: dict, payload: dict,
) -> None:
    response = client.post("/tasks", json=payload)

    assert response.status_code == 422
    assert "detail" in response.json()
    assert client.get("/tasks").json() == [task]


@pytest.mark.parametrize(
    "changes",
    [
        {"name": ""}, {"name": "   "}, {"name": None},
        {"priority": 0}, {"priority": 6}, {"priority": None},
        {"duration": 0}, {"duration": 11}, {"duration": None},
        {"due_date": "not-a-date"}, {"scheduled_date": "not-a-date"},
        {"completed": None},
        {"completed": "not-a-boolean"},
        # Name is applied first; a later operation error must roll it back.
        {"name": "Temporary", "duration": None},
    ],
)
def test_invalid_update_leaves_task_unchanged(
    client: TestClient, task: dict, changes: dict,
) -> None:
    response = client.patch(f"/tasks/{task['id']}", json=changes)

    assert response.status_code == 422
    assert "detail" in response.json()
    assert client.get("/tasks").json() == [task]


def test_delete_task(client: TestClient, task: dict) -> None:
    other = client.post(
        "/tasks", json={"name": "Physics", "priority": 1, "duration": 1}
    ).json()
    url = f"/tasks/{task['id']}"

    response = client.delete(url)

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(url).status_code == 404
    other = client.get(f"/tasks/{other['id']}").json()
    assert client.get("/tasks").json() == [other]
    assert client.delete(url).status_code == 404


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
def test_missing_task(client: TestClient, task: dict, method: str) -> None:
    response = client.request(
        method, "/tasks/999", **({"json": {"name": "Updated"}} if method == "PATCH" else {})
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Task 999 not found"}
    assert client.get("/tasks").json() == [task]


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
def test_invalid_task_id(client: TestClient, method: str) -> None:
    response = client.request(
        method, "/tasks/not-an-id", **({"json": {}} if method == "PATCH" else {})
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["path", "task_id"]


@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_malformed_json(client: TestClient, task: dict, method: str) -> None:
    url = "/tasks" if method == "POST" else f"/tasks/{task['id']}"

    response = client.request(
        method, url, content="{", headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422
    assert "detail" in response.json()
    assert client.get("/tasks").json() == [task]
