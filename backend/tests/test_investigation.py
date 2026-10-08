from fastapi.testclient import TestClient
from app.main import app
from app.services.research_service import ResearchService

client = TestClient(app)


def test_investigation_is_evidence_first(monkeypatch):
    monkeypatch.setattr(ResearchService, "search", lambda self, query: [])
    response = client.post(
        "/api/investigate",
        json={"text": "The Earth orbits the Sun."},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["verdict"] == "UNVERIFIED"
    assert data["confidence"] == 0
    assert data["evidence"] == []
    assert len(data["claims"]) == 1


def test_compound_claims_are_decomposed(monkeypatch):
    monkeypatch.setattr(ResearchService, "search", lambda self, query: [])
    response = client.post(
        "/api/investigate",
        json={"text": "Claim one; claim two."},
    )
    assert response.status_code == 200
    assert len(response.json()["claims"]) == 2
