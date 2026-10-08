from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_investigation():
    response = client.post(
        "/api/investigate",
        json={"text": "The Earth orbits the Sun."},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["verdict"] == "UNVERIFIED"
    assert len(data["claims"]) == 1
    assert data["evidence"] == []
