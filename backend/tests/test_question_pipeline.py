from fastapi.testclient import TestClient

from app.main import app
from app.services.research_service import ResearchService

client = TestClient(app)


def _doc(title, url, text):
    return {
        "title": title,
        "url": url,
        "source_score": 1.0,
        "source_type": "official_government",
        "text": text,
        "page_retrieved": True,
    }


def test_framed_questions_are_researched_and_synthesized(monkeypatch):
    calls = []

    def fake_search(self, question):
        calls.append(question)
        if "Prime Minister" in question:
            return [_doc("PMO", "https://pmindia.gov.in/en/prime-minister-of-india/", "Narendra Modi is the Prime Minister of India. The Prime Minister leads the Government of India.")]
        if "coalition" in question:
            return [_doc("Sansad", "https://sansad.in/", "The BJP-led NDA forms the Union Government of India.")]
        if "Lok Sabha" in question:
            return [_doc("ECI", "https://eci.gov.in/", "The 2024 Lok Sabha election results show the NDA won the election and formed the government.")]
        if "Does the party" in question:
            return [_doc("PMO", "https://pmindia.gov.in/en/prime-minister-of-india/", "Narendra Modi is the Prime Minister of India and leads the Government of India.")]
        return []

    monkeypatch.setattr(ResearchService, "search", fake_search)
    response = client.post("/api/investigate", json={"text": "Is Congress the central government in India in 2026?"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["research_questions"]) >= 4
    assert len(calls) == len(data["research_questions"])
    assert any(q["raw_answer"] for q in data["research_questions"])
    assert data["verdict"] in {"FALSE", "MOSTLY_FALSE", "UNVERIFIED"}
    assert len(data["evidence"]) > 0


def test_no_search_results_does_not_invent_raw_answers(monkeypatch):
    monkeypatch.setattr(ResearchService, "search", lambda self, question: [])
    response = client.post("/api/investigate", json={"text": "Is water wet?"})
    assert response.status_code == 200
    data = response.json()
    assert data["verdict"] == "UNVERIFIED"
    assert data["confidence"] == 0
    assert data["research_questions"]
    assert all("No source page was successfully retrieved" in q["raw_answer"] for q in data["research_questions"])
