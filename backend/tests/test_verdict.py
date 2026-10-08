from app.services.verdict_service import VerdictService


def ev(stance, domain, score=1.0, relevance=1.0, strength=1.0):
    return {
        "stance": stance,
        "domain": domain,
        "source_url": f"https://{domain}/article",
        "source_score": score,
        "relevance": relevance,
        "strength": strength,
    }


def test_strong_contradiction_can_produce_false():
    result = VerdictService().evaluate("Earth is flat", [
        ev("contradicting", "nasa.gov", 1.0),
        ev("contradicting", "noaa.gov", 1.0),
    ])
    assert result["verdict"] == "FALSE"
    assert result["confidence"] > 50


def test_strong_support_can_produce_true():
    result = VerdictService().evaluate("Water freezes at 0 degrees Celsius", [
        ev("supporting", "nasa.gov", 1.0),
        ev("supporting", "nih.gov", 1.0),
    ])
    assert result["verdict"] in {"TRUE", "MOSTLY_TRUE"}
    assert result["confidence"] > 50


def test_context_only_stays_insufficient():
    result = VerdictService().evaluate("Some claim", [ev("contextual", "example.com")])
    assert result["verdict"] == "INSUFFICIENT_EVIDENCE"
