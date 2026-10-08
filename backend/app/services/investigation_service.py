from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from urllib.parse import urlparse

from app.schemas.investigation import InvestigationResponse, ResearchQuestion
from app.services.claim_service import decompose_claim
from app.services.claim_intelligence import ClaimIntelligence
from app.services.question_service import QuestionService
from app.services.research_service import ResearchService
from app.services.evidence_service import EvidenceService
from app.services.verdict_service import VerdictService


def _raw_answer(question: str, documents: list[dict]) -> str:
    """Produce a question-level research answer from retrieved source text.

    This is deliberately not a verdict. It selects source-grounded passages
    that answer the framed question and preserves uncertainty when retrieval
    is insufficient.
    """
    if not documents:
        return "No source page was successfully retrieved for this question."

    terms = [t.lower() for t in re.findall(r"[a-zA-Z0-9]+", question) if len(t) >= 4]
    candidates: list[tuple[float, str, dict]] = []
    for doc in documents:
        text = re.sub(r"\s+", " ", doc.get("text", "")).strip()
        if not text:
            continue
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 45:
                continue
            lower = sentence.lower()
            hits = sum(1 for term in terms if term in lower)
            # Prefer sentences that answer the question, then primary sources.
            score = hits / max(2, len(terms))
            if any(x in lower for x in ("prime minister", "union government", "central government", "government of india", "lok sabha", "election", "formed the government", "forms the government")):
                score += .18
            score += min(.20, float(doc.get("source_score", 0)) * .20)
            candidates.append((score, sentence[:900], doc))

    if not candidates:
        return "Source pages were retrieved, but no usable textual passage was extracted."

    candidates.sort(key=lambda x: x[0], reverse=True)
    selected: list[str] = []
    domains: set[str] = set()
    for _, sentence, doc in candidates:
        domain = urlparse(doc.get("url", "")).netloc.lower()
        if sentence in selected:
            continue
        selected.append(sentence)
        if domain:
            domains.add(domain)
        if len(selected) >= 3:
            break

    source_note = ""
    if selected:
        top = candidates[0][2]
        source_note = f" Source: {top.get('title', 'retrieved source')} ({urlparse(top.get('url', '')).netloc.removeprefix('www.')})."
    return " ".join(selected) + source_note


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
            "Each framed question produces a source-grounded raw research answer",
            "Raw question answers remain separate from the final verdict",
            "The final synthesis answers the original investigation input, not the sub-questions",
            "Search results used for discovery; only retrieved page content enters evidence",
            "All question evidence combined and evaluated against the original claim",
            "Contradiction, scope, temporal and source-quality checks",
            "Evidence-weighted final verdict with uncertainty",
        ],
        claim_analysis=claim_analysis,
        evidence_analysis=verdict.get("analysis", {}),
        research_questions=question_models,
    )
