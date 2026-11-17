import pytest

from app.domain.availability import WEEKDAYS
from app import create_app
from app.repositories import AvailabilityRepository
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

def test_tc_3_14_enter_and_view_availability(client, db_connection, user_id):
     
    response = client.get("/availability")
    assert response.status_code == 200
    with client.session_transaction() as session:
        token = session["csrf_token"]

    for i, day in enumerate(WEEKDAYS):
        assert f'<label for="minutes_{i}">{day} (minutes)</label>'.encode() in response.data

    values = [120, 90, 60, 0, 45, 180, 240]
    form = {}
    for i, minutes in enumerate(values):
        form[f"minutes_{i}"] = str(minutes)
    form["csrf_token"] = token
    response = client.post("/availability", data=form, follow_redirects=True)
    assert b"Availability saved." in response.data

    client.get("/tasks")
    response = client.get("/availability")
    for i, minutes in enumerate(values):
        assert f'name="minutes_{i}" value="{minutes}"'.encode() in response.data
    assert AvailabilityRepository(db_connection).get_week(user_id) == values

    client.post("/auth/logout")
    with client.session_transaction() as session:
        session["user_id"] = user_id

    client.get("/tasks")
    response = client.get("/availability")
    for i, minutes in enumerate(values):
        assert f'name="minutes_{i}" value="{minutes}"'.encode() in response.data
    assert AvailabilityRepository(db_connection).get_week(user_id) == values

def test_tc_3_15_accept_availability_limits(client, db_connection, user_id):
    response = client.get("/availability")
    assert response.status_code == 200
    with client.session_transaction() as session:
        token = session["csrf_token"]
    
    values = [0, 1440, 60, 60, 60, 60, 60]
    form = {}
    for i, minutes in enumerate(values):
        form[f"minutes_{i}"] = str(minutes)
    form["csrf_token"] = token

    response = client.post("/availability", data=form, follow_redirects=True)
    assert b"Availability saved." in response.data
    assert b"Enter 0 to" not in response.data

    client.get("/tasks")
    response = client.get("/availability")
    for i, minutes in enumerate(values):
        assert f'name="minutes_{i}" value="{minutes}"'.encode() in response.data
    assert AvailabilityRepository(db_connection).get_week(user_id) == values

def test_tc_3_16_reject_invalid_availability(client, db_connection, user_id):
    AvailabilityRepository(db_connection).save_week(user_id, [60] * 7)
     
    response = client.get("/availability")
    assert response.status_code == 200
    with client.session_transaction() as session:
        token = session["csrf_token"]

    bad_values = ["-1", "1441", "90.5", "abc", ""]
    for bad in bad_values:
        form = {}
        for i, minutes in enumerate([60] * 7):
            form[f"minutes_{i}"] = str(minutes)
        form["minutes_0"] = bad
        form["csrf_token"] = token
        response = client.post("/availability", data=form)
        assert response.status_code == 400
        assert b"Enter 0 to 1440 minutes for Monday." in response.data
        assert AvailabilityRepository(db_connection).get_week(user_id) == [60] * 7


    client.get("/tasks")
    response = client.get("/availability")
    for i, minutes in enumerate([60] * 7):
        assert f'name="minutes_{i}" value="{minutes}"'.encode() in response.data
