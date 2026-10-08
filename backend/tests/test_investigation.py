from fastapi.testclient import TestClient
from app.main import app
from app.services.investigation_service import ResearchService

client = TestClient(app)


def test_investigation_uses_evidence(monkeypatch):
    def fake_search(self, query):
        return [{
            "title": "Official source",
            "url": "https://nasa.gov/example",
            "text": "Earth is approximately spherical and is not flat.",
            "source_score": 1.0,
            "source_type": "official",
            "source_tier": 1,
            "retrieved": True,
        }]

    monkeypatch.setattr(ResearchService, "search", fake_search)
    response = client.post("/api/investigate", json={"text": "Earth is flat"})
    assert response.status_code == 200
    data = response.json()
    assert data["verdict"] in {"FALSE", "MOSTLY_FALSE"}
    assert data["confidence"] > 0
    assert data["evidence"]
    assert data["evidence"][0]["stance"] == "contradicting"


def test_investigation_no_results_is_unverified(monkeypatch):
    monkeypatch.setattr(ResearchService, "search", lambda self, query: [])
    response = client.post("/api/investigate", json={"text": "An unsupported claim"})
    assert response.status_code == 200
    data = response.json()
    assert data["verdict"] == "UNVERIFIED"
    assert data["confidence"] == 0
    assert data["evidence"] == []


def test_compound_claims_are_decomposed(monkeypatch):
    monkeypatch.setattr(ResearchService, "search", lambda self, query: [])
    response = client.post("/api/investigate", json={"text": "Claim one; claim two."})
    assert response.status_code == 200
    assert len(response.json()["claims"]) == 2
