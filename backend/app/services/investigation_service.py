from app.schemas.investigation import InvestigationResponse
from app.services.claim_service import decompose_claim
from app.services.research_service import ResearchService
from app.services.evidence_service import EvidenceService
from app.services.verdict_service import VerdictService


def investigate(text: str) -> InvestigationResponse:
    claims = decompose_claim(text)

    researcher = ResearchService()
    evidence_service = EvidenceService()
    verdict_service = VerdictService()

    documents = researcher.search(text)
    evidence = evidence_service.extract(documents, text)
    verdict = verdict_service.evaluate(text, evidence)

    return InvestigationResponse(
        claim=text,
        claims=claims,
        verdict=verdict["verdict"],
        confidence=verdict["confidence"],
        explanation=verdict["explanation"],
        evidence=evidence,
        sources=researcher.normalize(documents),
        status="research_not_configured" if not documents else "complete",
        methodology=[
            "Claim decomposition",
            "Evidence-first verification",
            "No verdict without evidence",
        ],
    )
