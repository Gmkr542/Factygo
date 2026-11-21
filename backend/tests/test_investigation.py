from fastapi.testclient import TestClient
from app.main import app
import app.services.investigation_service as inv_mod

client = TestClient(app)


def test_investigation_is_evidence_first(monkeypatch):
    async def empty_search(query, max_results=5, resource_plan=None):
        return []

    monkeypatch.setattr(inv_mod, "search_web", empty_search)
    response = client.post(
        "/api/investigate",
        json={"text": "Unique uncached claim xyz123."},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["verdict"] == "UNVERIFIED"
    assert data["confidence"] == 0
    assert data["evidence"] == []
    assert len(data["claims"]) == 1


def test_compound_claims_are_decomposed(monkeypatch):
    async def empty_search(query, max_results=5, resource_plan=None):
        return []

    monkeypatch.setattr(inv_mod, "search_web", empty_search)
    response = client.post(
        "/api/investigate",
        json={"text": "Claim one is longer; claim two is also longer."},
    )
    assert response.status_code == 200
    assert len(response.json()["claims"]) == 2


def test_congress_claim_can_be_contradicted_by_authoritative_pm_record():
    from app.services.evidence_service import EvidenceService
    evidence = EvidenceService().extract([
        {
            "title": "Prime Minister of India",
            "url": "https://www.pmindia.gov.in/en/prime-minister-of-india/",
            "source_score": 1.0,
            "source_type": "Government / Official",
            "text": "Narendra Modi is the Prime Minister of India. The Prime Minister leads the Government of India.",
        }
    ], "is congress central government in India 2026?")
    assert any(item["stance"] == "contradicting" for item in evidence)
    assert not any(item["stance"] == "supporting" for item in evidence)
