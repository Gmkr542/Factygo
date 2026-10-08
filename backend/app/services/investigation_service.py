from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import re

from app.schemas.investigation import InvestigationResponse, ResearchQuestion
from app.services.claim_service import decompose_claim
from app.services.claim_intelligence import ClaimIntelligence
from app.services.question_service import QuestionService
from app.services.research_service import ResearchService
from app.services.evidence_service import EvidenceService
from app.services.verdict_service import VerdictService


def _raw_answer(question: str, documents: list[dict]) -> str:
    """Return a source-grounded raw research answer, without synthesizing a verdict."""
    if not documents:
        return "No source page was successfully retrieved for this question."

    snippets: list[str] = []
    terms = [t.lower() for t in re.findall(r"[a-zA-Z0-9]+", question) if len(t) >= 4]
    for doc in documents:
        text = re.sub(r"\s+", " ", doc.get("text", "")).strip()
        if not text:
            continue
        sentences = re.split(r"(?<=[.!?])\s+", text)
        ranked = sorted(
            (s.strip() for s in sentences if len(s.strip()) >= 45),
            key=lambda s: sum(1 for t in terms if t in s.lower()),
            reverse=True,
        )
        for sentence in ranked[:2]:
            if sentence not in snippets:
                snippets.append(sentence[:700])
        if len(snippets) >= 3:
            break

    if not snippets:
        return "Source pages were retrieved, but no usable textual passage was extracted."
    return " ".join(snippets[:3])


def investigate(text: str) -> InvestigationResponse:
    claims = decompose_claim(text)
    claim_analysis = ClaimIntelligence.analyze(text)
    questions = QuestionService.frame(text, claim_analysis)
    researcher = ResearchService()
    evidence_service = EvidenceService()
    verdict_service = VerdictService()

    # Each framed question is independently researched. This is the research
    # layer; it does not decide the original claim.
    results: list[tuple[int, str, list[dict]]] = []

    def research_one(item: tuple[int, str]) -> tuple[int, str, list[dict]]:
        index, question = item
        try:
            return index, question, researcher.search(question)
        except Exception:
            return index, question, []

    with ThreadPoolExecutor(max_workers=min(5, len(questions) or 1)) as pool:
        futures = [pool.submit(research_one, item) for item in enumerate(questions, start=1)]
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda x: x[0])

    # Deduplicate source documents across question research while retaining
    # which questions generated the research.
    documents: list[dict] = []
    seen_urls: set[str] = set()
    question_models: list[ResearchQuestion] = []
    for index, question, docs in results:
        unique_docs = []
        for doc in docs:
            url = doc.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                documents.append(doc)
            if url and url not in {d.get("url") for d in unique_docs}:
                unique_docs.append(doc)
        question_models.append(
            ResearchQuestion(
                id=index,
                question=question,
                raw_answer=_raw_answer(question, docs),
                sources=researcher.normalize(docs),
                evidence_count=len(docs),
                status="researched" if docs else "no_results",
            )
        )

    # Final evidence analysis is performed against the ORIGINAL investigation
    # input, using the complete evidence pool produced by all sub-questions.
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
        status="complete" if documents else "no_results",
        methodology=[
            "Claim understanding: subject, jurisdiction and time",
            "Investigation broken into independently researchable questions",
            "Each question researched separately across the web",
            "Raw answers retained as source-grounded research, not verdicts",
            "Search results used for discovery; only retrieved page content enters evidence",
            "All question evidence combined and evaluated against the original claim",
            "Contradiction, scope, temporal and source-quality checks",
            "Evidence-weighted final verdict with uncertainty",
        ],
        claim_analysis=claim_analysis,
        evidence_analysis=verdict.get("analysis", {}),
        research_questions=question_models,
    )
