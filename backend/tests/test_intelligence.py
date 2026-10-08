from app.services.claim_intelligence import ClaimIntelligence
from app.services.evidence_service import EvidenceService
from app.services.verdict_service import VerdictService


def test_union_scope_is_detected():
    meta = ClaimIntelligence.analyze("Is Congress the central government in India in 2026?")
    assert meta["jurisdiction"] == "UNION"
    assert meta["year"] == 2026
    assert meta["subject"] == "Indian National Congress"


def test_state_evidence_does_not_support_union_claim():
    claim = "Is Congress the central government in India in 2026?"
    documents = [{
        "title": "Kerala government",
        "url": "https://example.com/kerala",
        "source_score": 0.8,
        "text": "The Congress-led United Democratic Front is ruling Kerala in 2026."
    }]
    evidence = EvidenceService().extract(documents, claim)
    assert evidence
    assert evidence[0]["stance"] == "contextual"
    assert evidence[0]["jurisdiction_match"] is False


def test_direct_union_contradiction_beats_state_context():
    claim = "Is Congress the central government in India in 2026?"
    evidence = [
        {"stance": "contextual", "strength": .9, "source_score": .8, "source_url": "https://state.example/a"},
        {"stance": "contradicting", "strength": .95, "source_score": 1.0, "source_url": "https://eci.gov.in/a", "jurisdiction_match": True},
        {"stance": "contradicting", "strength": .90, "source_score": .9, "source_url": "https://sansad.in/b", "jurisdiction_match": True},
    ]
    result = VerdictService().evaluate(claim, evidence)
    assert result["verdict"] == "FALSE"
    assert result["confidence"] >= 80
