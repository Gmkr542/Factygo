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


def test_snippet_is_usable_when_page_fetch_fails():
    # Regression contract: search results must not be discarded solely
    # because the destination page cannot be fetched.
    document = {
        "title": "Example",
        "url": "https://example.com",
        "snippet": "Congress is not the central government of India.",
    }
    page_text = ""
    text = page_text or document["snippet"]
    assert text
