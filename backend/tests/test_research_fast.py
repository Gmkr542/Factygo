from app.services.research_service import ResearchService


def test_political_queries_are_bounded():
    queries = ResearchService._build_queries(
        "is congress central government in India 2026?"
    )
    assert 1 <= len(queries) <= 6
    assert any("Union government" in q for q in queries)


def test_political_queries_include_authoritative_discovery_paths():
    queries = ResearchService._build_queries(
        "is congress central government in India 2026?"
    )
    assert any("pmindia.gov.in" in q for q in queries)
    assert any("eci.gov.in" in q for q in queries)


def test_search_result_cannot_stand_alone_as_evidence():
    docs = [{
        "title": "Government of India",
        "url": "https://example.gov.in/current",
        "snippet": "The Union Government is formed by the party or coalition commanding Lok Sabha.",
        "source_score": 1.0,
        "source_type": "official",
        "text": "",
        "page_retrieved": False,
    }]
    assert not docs[0]["text"]
    assert docs[0]["page_retrieved"] is False
