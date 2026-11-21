from fastapi.testclient import TestClient
from app.main import app
import app.services.investigation_service as inv_mod

client = TestClient(app)


def _doc(title, url, text):
    return {
        "title": title,
        "url": url,
        "domain": "pmindia.gov.in",
        "source_score": 1.0,
        "source_quality": 95,
        "source_type": "Government / Official",
        "content": text,
        "text": text,
        "relevance_score": 85,
    }


def test_framed_questions_are_researched_and_synthesized(monkeypatch):
    calls = []

    async def fake_search(question, max_results=5, resource_plan=None):
        calls.append(question)
        return [_doc("PMO", "https://pmindia.gov.in/en/prime-minister-of-india/", "Narendra Modi is the Prime Minister of India. The Prime Minister leads the Government of India.")]

    monkeypatch.setattr(inv_mod, "search_web", fake_search)
    monkeypatch.setattr(inv_mod, "_enrich_top_articles", lambda docs: None)
    response = client.post("/api/investigate", json={"text": "Is Congress the central government in India in 2026?"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["research_questions"]) >= 2
    assert len(calls) >= 2
    assert any(q["raw_answer"] for q in data["research_questions"])
    assert data["verdict"] in {"FALSE", "MOSTLY FALSE", "MISLEADING", "UNVERIFIED"}
    assert len(data["evidence"]) > 0
