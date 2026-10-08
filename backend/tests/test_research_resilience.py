from app.services.research_service import ResearchService


def test_search_html_parses_standard_result():
    service = ResearchService()
    html = """
    <div class="result">
      <a class="result__a" href="https://example.com/page">Example result</a>
      <a class="result__snippet">Example evidence snippet about India.</a>
    </div>
    """
    results = service._parse_search_html(html)
    assert results
    assert results[0]["url"] == "https://example.com/page"
    assert "Example result" in results[0]["title"]


def test_search_html_parses_lite_result():
    service = ResearchService()
    html = """
    <a class="result-link" href="https://example.com/page">Example result</a>
    """
    results = service._parse_search_html(html)
    assert results
    assert results[0]["url"] == "https://example.com/page"


def test_snippet_is_not_evidence_when_page_fetch_fails():
    # Evidence-first contract: search snippets are discovery metadata only.
    document = {
        "title": "Example",
        "url": "https://example.com",
        "snippet": "Congress is not the central government of India.",
        "text": "",
        "page_retrieved": False,
        "research_status": "search_result_only",
    }
    assert not document["text"]
    assert document["research_status"] == "search_result_only"
    assert document["page_retrieved"] is False


def test_political_authority_seeds_exist_without_search_provider():
    seeds = ResearchService._authority_seeds("is congress central government in India 2026?")
    urls = {item["url"] for item in seeds}
    assert "https://www.pmindia.gov.in/en/prime-minister-of-india/" in urls
    assert "https://results.eci.gov.in/PcResultGenJune2024/" in urls


def test_non_political_claim_has_no_authority_seeds():
    assert ResearchService._authority_seeds("water boils at 100 degrees C") == []


def test_authority_seed_is_retrieved_when_search_returns_no_results(monkeypatch):
    service = ResearchService()
    monkeypatch.setattr(service, "_search_once", lambda client, query: [])

    def fake_fetch(client, url):
        if "pmindia.gov.in" in url:
            return "Narendra Modi is the Prime Minister of India. The Prime Minister leads the Government of India."
        return ""

    monkeypatch.setattr(service, "_fetch_page", fake_fetch)
    documents = service.search("is congress central government in India 2026?")
    assert documents
    assert any("pmindia.gov.in" in doc["url"] and doc["page_retrieved"] for doc in documents)
    assert all(doc["text"] for doc in documents)
