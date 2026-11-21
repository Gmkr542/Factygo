from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

from app.core.config import get_settings
from app.schemas.investigation import Claim, InvestigationResponse, ResearchQuestion
from app.services.claim_intelligence import ClaimIntelligence
from app.services.claim_service import decompose_claim
from app.services.evidence_service import EvidenceService
from app.services.groq_service import (
    breakdown_questions,
    decompose_claims,
    plan_resources,
    synthesize_investigation,
)
from app.services.question_service import QuestionService
from app.services.search_service import ResearchService, search_web
from app.services.verdict_service import VerdictService

logger = logging.getLogger(__name__)


def _raw_answer(question: str, documents: list[dict]) -> str:
    if not documents:
        return "No source page was retrieved for this research question."
    top = documents[0]
    snippet = str(top.get("content") or top.get("text") or "").strip()[:500]
    domain = urlparse(top.get("url", "")).netloc.removeprefix("www.")
    if not snippet:
        snippet = top.get("title", "Relevant source found.")
    return f"{snippet} (Source: {top.get('title', 'Retrieved source')} — {domain})"


async def investigate_async(text: str) -> InvestigationResponse:
    settings = get_settings()
    claim_analysis = ClaimIntelligence.analyze(text)
    use_ai = bool(settings.groq_api_key and settings.groq_api_key.strip())

    # 1. Claim decomposition (LLM with deterministic fallback)
    claims: list[Claim] = []
    if use_ai:
        try:
            ai_claims = await decompose_claims(text)
            claims = [
                Claim(id=i, text=c["claim"], type=c.get("type", "statement"))
                for i, c in enumerate(ai_claims, start=1)
            ]
        except Exception as exc:
            logger.warning("LLM claim decomposition failed, using fallback: %s", exc)
    if not claims:
        claims = decompose_claim(text)

    # 2. Research question framing (LLM with clean keyword fallback)
    questions: list[str] = []
    if use_ai:
        try:
            questions = await breakdown_questions(text)
        except Exception as exc:
            logger.warning("LLM question breakdown failed, using fallback: %s", exc)
    if not questions:
        questions = QuestionService.frame(text, claim_analysis)

    # 3. Context-aware resource planning
    resource_plan: dict = {}
    if use_ai:
        try:
            resource_plan = await plan_resources(text, questions)
        except Exception as exc:
            logger.warning("LLM resource planning failed: %s", exc)

    # 4. Concurrent multi-provider web search (DDGS + Google News RSS)
    search_tasks = [search_web(q, resource_plan=resource_plan) for q in questions]
    batch_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    documents: list[dict] = []
    seen_urls: set[str] = set()
    docs_by_question: list[tuple[int, str, list[dict]]] = []

    for idx, (question, res) in enumerate(zip(questions, batch_results), start=1):
        if isinstance(res, Exception):
            logger.exception("Search failed for question %r: %s", question, res)
            docs = []
        else:
            docs = res
        docs_by_question.append((idx, question, docs))
        for doc in docs:
            url = doc.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                enriched = dict(doc)
                enriched["research_question"] = question
                documents.append(enriched)

    # Sort combined pool by relevance & source quality and assign stable E01..E15 IDs
    documents.sort(
        key=lambda x: (x.get("relevance_score", 0), x.get("source_quality", 0)),
        reverse=True,
    )
    documents = documents[:15]
    for i, doc in enumerate(documents, start=1):
        doc["evidence_id"] = f"E{i:02d}"

    # 5. Synthesis & Evidence Extraction (Groq AI with deterministic fallback)
    llm_synthesis: dict = {}
    if use_ai and documents:
        try:
            llm_synthesis = await synthesize_investigation(text, questions, documents)
        except Exception as exc:
            logger.warning("LLM synthesis failed, falling back to deterministic verdict: %s", exc)

    evidence_service = EvidenceService()
    evidence = evidence_service.extract(
        documents,
        text,
        llm_assessments=llm_synthesis.get("evidence_assessments"),
    )

    if llm_synthesis and llm_synthesis.get("verdict"):
        verdict_label = str(llm_synthesis["verdict"]).upper()
        try:
            confidence = max(0, min(100, int(round(float(llm_synthesis.get("confidence", 0))))))
        except (TypeError, ValueError):
            confidence = 50
        explanation = str(llm_synthesis.get("explanation") or "").strip()
        evidence_analysis = llm_synthesis.get("analysis") if isinstance(llm_synthesis.get("analysis"), dict) else {}
    else:
        verdict_data = VerdictService().evaluate(text, evidence)
        verdict_label = verdict_data["verdict"]
        confidence = verdict_data["confidence"]
        explanation = verdict_data["explanation"]
        evidence_analysis = verdict_data["analysis"]

    # Map LLM question answers if available
    ai_q_answers = {
        str(item.get("question", "")).strip().lower(): str(item.get("answer", "")).strip()
        for item in llm_synthesis.get("question_answers", [])
        if isinstance(item, dict) and item.get("answer")
    }

    researcher = ResearchService()
    question_models: list[ResearchQuestion] = []
    for idx, question, docs in docs_by_question:
        ans = ai_q_answers.get(question.lower()) or _raw_answer(question, docs)
        question_models.append(
            ResearchQuestion(
                id=idx,
                question=question,
                raw_answer=ans,
                sources=researcher.normalize(docs),
                evidence_count=len(docs),
                status="researched" if docs else "no_results",
            )
        )

    return InvestigationResponse(
        claim=text,
        claims=claims,
        verdict=verdict_label,
        confidence=confidence,
        explanation=explanation,
        evidence=evidence,
        sources=researcher.normalize(documents),
        status="complete" if documents else "no_results",
        methodology=[
            "Claim normalization and atomic decomposition",
            "Context-aware research question framing & resource planning",
            "Concurrent multi-provider live web search (DDGS + Google News RSS)",
            "Source authority classification and URL deduplication",
            "Evidence-grounded AI synthesis with deterministic fallback",
        ],
        claim_analysis=claim_analysis,
        evidence_analysis=evidence_analysis,
        research_questions=question_models,
    )


def investigate(text: str) -> InvestigationResponse:
    return asyncio.run(investigate_async(text))
