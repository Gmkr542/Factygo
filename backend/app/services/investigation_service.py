from app.schemas.investigation import InvestigationResponse
from app.services.claim_service import decompose_claim
from app.services.claim_intelligence import ClaimIntelligence
from app.services.research_service import ResearchService
from app.services.evidence_service import EvidenceService
from app.services.verdict_service import VerdictService


def investigate(text: str) -> InvestigationResponse:
    claims = decompose_claim(text)
    claim_analysis = ClaimIntelligence.analyze(text)
    researcher = ResearchService()
    evidence_service = EvidenceService()
    verdict_service = VerdictService()
    documents = researcher.search(text)
    evidence = evidence_service.extract(documents, text)
    verdict = verdict_service.evaluate(text, evidence)
    return InvestigationResponse(
        claim=text, claims=claims, verdict=verdict["verdict"], confidence=verdict["confidence"],
        explanation=verdict["explanation"], evidence=evidence, sources=researcher.normalize(documents),
        status="complete" if documents else "no_results",
        methodology=["Claim understanding: subject, jurisdiction and time", "Claim-aware web research", "Scope and temporal evidence matching", "Source authority ranking", "Evidence stance and corroboration", "Evidence-weighted verdict with uncertainty"],
        claim_analysis=claim_analysis, evidence_analysis=verdict.get("analysis", {}),
    )
