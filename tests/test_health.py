import pytest
from app import create_app
from tests.fake_auth import FakeAuthClient

@pytest.fixture
def client():
    app = create_app({"SUPABASE_CLIENT": FakeAuthClient()})
    app.config.update({
        "TESTING": True
    })

    with app.test_client() as client:
        yield client

def test_app_is_running(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "healthy"}
