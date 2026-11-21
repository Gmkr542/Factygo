from app.services.citation_auditor import CitationAuditor
from app.services.evidence_service import classify_study_tier
from app.services.investigation_service import _sanitize_visual_blocks
from app.services.logic_service import LogicService
from app.services.search_service import _clean_text, _normalise


def test_citation_detector_finds_doi_pmid_arxiv():
    sample = "See DOI: 10.1038/s41586-023-99999-z, PMID: 12345678, and arXiv:1706.03762."
    found = CitationAuditor.detect_citations(sample)
    assert "10.1038/s41586-023-99999-z" in found["dois"]
    assert "12345678" in found["pmids"]
    assert "1706.03762" in found["arxivs"]


def test_logic_service_arithmetic_and_units():
    facts = LogicService.analyze("25% of 400 is 100 and 10 crore people travel at 60 mph", [])
    joined = " | ".join(facts)
    assert "25% of 400 = 100" in joined
    assert "10 crore = 100,000,000" in joined
    assert "60 mph = 96.56 km/h" in joined


def test_evidence_pyramid_classification():
    t1, r1 = classify_study_tier("Randomized Controlled Trial of Green Tea", "Double-blind study", "Academic / Reference")
    t3, r3 = classify_study_tier("Lemon extract in mouse model", "Tested in vitro and mice", "Academic / Reference")
    assert r1 == 1 and "Meta-Analysis / RCT" in t1
    assert r3 == 3 and "Preclinical / Animal" in t3


def test_syndication_deduplication_and_html_unescape():
    raw = [
        {"title": "India overtakes China &nbsp; UN report", "url": "https://a.com/1", "body": "Text &nbsp; one"},
        {"title": "India overtakes China UN report", "url": "https://b.com/2", "body": "Syndicated copy"},
    ]
    norm = _normalise(raw)
    assert len(norm) == 1
    assert "&nbsp;" not in norm[0]["title"]
    assert "&nbsp;" not in norm[0]["content"]


def test_visual_block_sanitizer():
    blocks = _sanitize_visual_blocks([
        {"type": "table", "title": "Compare", "headers": ["A", "B"], "rows": [["1", "2"]]},
        {"type": "invalid_type", "title": "Bad"},
    ])
    assert len(blocks) == 1
    assert blocks[0]["type"] == "table"
