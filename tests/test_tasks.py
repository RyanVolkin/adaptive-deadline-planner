from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app import create_app
from app.repositories import TaskRepository
from app.routes import tasks as task_routes
from app.task import Task
from tests.fake_auth import FakeAuthClient


@pytest.fixture
def client(db_connection, db_url, user_id):
    app = create_app({
        "TESTING": True, "SECRET_KEY": "test",
        "SUPABASE_CLIENT": FakeAuthClient(), "DATABASE_URL": db_url,
    })
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client


def task_form(client):
    assert client.get("/tasks/new").status_code == 200
    with client.session_transaction() as session:
        token = session["csrf_token"]
    return {
        "name": "Essay", "type": "homework", "priority": "medium",
        "deadline": "2099-12-31", "original_estimate": "600",
        "csrf_token": token,
    }


def test_create_edit_and_delete_task(client, db_connection, user_id):
    data = task_form(client)
    response = client.post("/tasks/new", data=data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Essay" in response.data
    assert b"Task added." in response.data
    for heading in ("Name", "Type", "Due", "Priority", "Estimate", "Adjusted",
                    "Remaining", "Done", "State"):
        assert f"<th>{heading}</th>".encode() in response.data
    assert response.data.count(b"<td>10h 00m</td>") == 3
    tasks = TaskRepository(db_connection)
    task = tasks.list_by_user(user_id)[0]
    assert task.user_id == user_id
    assert client.get(f"/tasks/{task.id}/edit").status_code == 200

    data.update(name="Revised essay", original_estimate="300")
    response = client.post(f"/tasks/{task.id}/edit", data=data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Revised essay" in response.data
    assert b"Task updated." in response.data
    assert tasks.get(user_id, task.id).remaining_work == 300

    response = client.get(f"/tasks/{task.id}/delete")
    assert response.status_code == 200
    assert b"Revised essay" in response.data
    assert b"work records and schedule entries" in response.data
    assert b'name="confirmed" value="yes"' in response.data
    assert tasks.get(user_id, task.id) is not None

    response = client.post(f"/tasks/{task.id}/delete", data={
        "csrf_token": data["csrf_token"], "confirmed": "yes",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert tasks.list_by_user(user_id) == []
    assert b"No tasks yet." in response.data
    assert b"Task deleted." in response.data


def test_task_validation_keeps_form_values(client, db_connection, user_id):
    data = task_form(client)
    data["original_estimate"] = "0"
    response = client.post("/tasks/new", data=data)
    assert response.status_code == 400
    assert b"positive whole number" in response.data
    assert b'value="Essay"' in response.data
    assert TaskRepository(db_connection).list_by_user(user_id) == []


def test_other_users_task_is_not_accessible(client, db_connection, user_id, other_user_id):
    data = task_form(client)
    client.post("/tasks/new", data=data)
    tasks = TaskRepository(db_connection)
    task = tasks.list_by_user(user_id)[0]
    with client.session_transaction() as session:
        session["user_id"] = other_user_id

    assert b"Essay" not in client.get("/tasks").data
    assert client.get(f"/tasks/{task.id}/edit").status_code == 404
    assert client.post(f"/tasks/{task.id}/edit", data=data).status_code == 404
    assert client.get(f"/tasks/{task.id}/delete").status_code == 404
    assert client.post(f"/tasks/{task.id}/delete", data={
        "csrf_token": data["csrf_token"], "confirmed": "yes",
    }).status_code == 404
    assert client.post(f"/tasks/{task.id}/delete", data={
        "csrf_token": data["csrf_token"],
    }).status_code == 404
    assert tasks.get(user_id, task.id).name == "Essay"


def test_missing_task_returns_not_found(client):
    data = task_form(client)
    for action in ("edit", "delete"):
        assert client.get(f"/tasks/999999/{action}").status_code == 404
        assert client.post(f"/tasks/999999/{action}", data=data).status_code == 404


def test_delete_needs_confirmation(client, db_connection, user_id):
    data = task_form(client)
    client.post("/tasks/new", data=data)
    tasks = TaskRepository(db_connection)
    task = tasks.list_by_user(user_id)[0]
    response = client.post(f"/tasks/{task.id}/delete", data={"csrf_token": data["csrf_token"]})
    assert response.status_code == 400
    assert b"Confirm task deletion" in response.data
    assert tasks.get(user_id, task.id) is not None


def test_task_posts_require_form_token(client, db_connection, user_id):
    data = task_form(client)
    client.post("/tasks/new", data=data)
    tasks = TaskRepository(db_connection)
    task = tasks.list_by_user(user_id)[0]
    del data["csrf_token"]
    assert client.post("/tasks/new", data=data).status_code == 400
    assert client.post(f"/tasks/{task.id}/edit", data=data).status_code == 400
    assert client.post(f"/tasks/{task.id}/delete", data={"confirmed": "yes"}).status_code == 400
    assert tasks.list_by_user(user_id) == [task]


def test_tasks_require_login():
    app = create_app({"TESTING": True, "SECRET_KEY": "test", "SUPABASE_CLIENT": FakeAuthClient()})
    client = app.test_client()
    assert client.get("/tasks").headers["Location"] == "/auth/login"
    assert client.post("/tasks/new", data={}).headers["Location"] == "/auth/login"


def test_task_pages_use_configured_local_date(monkeypatch):
    now = datetime(2026, 10, 21, 2, tzinfo=timezone.utc)
    monkeypatch.setattr(task_routes, "datetime", SimpleNamespace(
        now=lambda zone: now.astimezone(zone),
    ))
    task = Task(
        id=1, user_id="test-user", name="Essay", type="homework", priority="medium",
        deadline=date(2026, 10, 20), original_estimate=120, starting_estimate=120,
        adjusted_estimate=90, remaining_work=45, completion_pct=50,
        created_at=now, updated_at=now,
    )
    monkeypatch.setattr(task_routes, "_task_service", lambda: SimpleNamespace(
        list_tasks=lambda user_id: [task],
    ))
    app = create_app({
        "TESTING": True, "SECRET_KEY": "test", "SUPABASE_CLIENT": FakeAuthClient(),
        "APP_TIMEZONE": "America/New_York",
    })
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = task.user_id

    assert b'min="2026-10-20"' in client.get("/tasks/new").data
    response = client.get("/tasks")
    assert response.status_code == 200
    assert b"<td>Active</td>" in response.data
    assert b"<td>2h 00m</td>" in response.data
    assert b"<td>1h 30m</td>" in response.data
    assert b"<td>0h 45m</td>" in response.data
    assert b"<td>50%</td>" in response.data
