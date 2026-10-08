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


def test_congress_claim_can_be_contradicted_by_authoritative_pm_record():
    from app.services.evidence_service import EvidenceService
    evidence = EvidenceService().extract([
        {
            "title": "Prime Minister of India",
            "url": "https://www.pmindia.gov.in/en/prime-minister-of-india/",
            "source_score": 1.0,
            "source_type": "official_government",
            "text": "Narendra Modi is the Prime Minister of India. The Prime Minister leads the Government of India.",
            "page_retrieved": True,
        }
    ], "is congress central government in India 2026?")
    assert any(item["stance"] == "contradicting" for item in evidence)

def test_generic_pm_statement_is_not_support_for_congress_claim():
    from app.services.evidence_service import EvidenceService
    evidence = EvidenceService().extract([
        {
            "title": "Prime Minister of India",
            "url": "https://www.pmindia.gov.in/en/prime-minister-of-india/",
            "source_score": 1.0,
            "source_type": "official_government",
            "text": "Narendra Modi is the Prime Minister of India. The Prime Minister leads the Government of India.",
            "page_retrieved": True,
        }
    ], "Is Congress the central government in India in 2026?")
    assert any(item["stance"] == "contradicting" for item in evidence)
    assert not any(item["stance"] == "supporting" for item in evidence)
