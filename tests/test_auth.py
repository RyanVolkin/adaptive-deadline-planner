from app import create_app
from tests.fake_auth import FakeAuthClient


def test_registration_login_and_logout():
    app = create_app({"TESTING": True, "SECRET_KEY": "test", "SUPABASE_CLIENT": FakeAuthClient()})
    client = app.test_client()

    response = client.post(
        "/auth/register",
        data={"email": "planner@example.com", "password": "password123"},
    )
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session["user_id"] == "1"
    response = client.get("/")
    assert b"Logged in user ID: <code>1</code>" in response.data

    response = client.post(
        "/auth/login", data={"email": "planner@example.com", "password": "password123"}
    )
    assert response.status_code == 302

    response = client.post(
        "/auth/login", data={"email": "planner@example.com", "password": "incorrect"}
    )
    assert response.status_code == 200
    assert b"Invalid email or password." in response.data

    response = client.post("/auth/logout")
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert "user_id" not in session


def test_registration_validates_password_and_duplicate_email():
    app = create_app({"TESTING": True, "SECRET_KEY": "test", "SUPABASE_CLIENT": FakeAuthClient()})
    client = app.test_client()

    response = client.post(
        "/auth/register",
        data={"email": "valid@example.com", "password": "short"},
    )
    assert response.status_code == 200
    assert b"Password must be" in response.data

    client.post(
        "/auth/register",
        data={"email": "valid@example.com", "password": "password123"},
    )
    response = client.post(
        "/auth/register",
        data={"email": "valid@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    assert b"Unable to create account." in response.data


def test_index_login_link_opens_login_page():
    app = create_app({"TESTING": True, "SECRET_KEY": "test", "SUPABASE_CLIENT": FakeAuthClient()})
    client = app.test_client()

    response = client.get("/")

    assert b'<form action="/auth/login" method="get">' in response.data
    assert client.get("/auth/login").status_code == 200