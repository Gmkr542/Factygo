from __future__ import annotations

import asyncio
import logging
import re
import time
from urllib.parse import urlparse

from app.core.config import get_settings
from app.schemas.investigation import InvestigationResponse, ResearchQuestion
from app.services.claim_intelligence import ClaimIntelligence
from app.services.claim_service import decompose_claim
from app.services.evidence_service import EvidenceService
from app.services.groq_service import synthesize_investigation
from app.services.question_service import QuestionService
from app.services.search_service import ResearchService, search_web
from app.services.verdict_service import VerdictService

logger = logging.getLogger(__name__)

_INVESTIGATION_CACHE: dict[str, tuple[float, InvestigationResponse]] = {}
_CACHE_TTL_SECONDS = 3600  # 1 hour cache so repeat/demo clicks use 0 Groq tokens

_DOMAIN_BY_CATEGORY = {
    "health": ["pubmed.ncbi.nlm.nih.gov", "who.int", "nih.gov"],
    "health_science": ["pubmed.ncbi.nlm.nih.gov", "who.int", "nih.gov"],
    "medical": ["pubmed.ncbi.nlm.nih.gov", "who.int", "nih.gov"],
    "science": ["nature.com", "pubmed.ncbi.nlm.nih.gov", "arxiv.org"],
    "finance": ["imf.org", "worldbank.org", "sec.gov"],
    "economics_finance": ["imf.org", "worldbank.org", "sec.gov"],
    "politics": ["reuters.com", "apnews.com", "bbc.com"],
}


def _raw_answer(question: str, documents: list[dict]) -> str:
    if not documents:
        return "No source page was retrieved for this research question."
    top = documents[0]
    snippet = str(top.get("content") or top.get("text") or "").strip()[:260]
    domain = top.get("domain") or urlparse(top.get("url", "")).netloc.removeprefix("www.")
    if not snippet:
        snippet = top.get("title", "Relevant source found.")
    return f"{snippet} ({top.get('title', 'Source')} — {domain})"


def _format_quick_report(verdict: str, claim: str, raw_text: str) -> str:
    cleaned = " ".join(str(raw_text or "").split()).strip()
    title_verdict = verdict.title()
    cleaned = re.sub(
        r"^Result\s*:\s*(?:TRUE|MOSTLY TRUE|PARTLY TRUE|MISLEADING|MOSTLY FALSE|FALSE|UNVERIFIED)?\s*[,:\-–]?\s*",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(
        r"^(?:the claim that\s+.+?\s+is\s+(?:contradicted|supported|refuted)\s+by\s+.+?(?:indicating|showing|stating)\s+that\s+)",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r",?\s*making the claim (?:false|true|misleading)\.?$", ".", cleaned, flags=re.I)
    if cleaned:
        cleaned = cleaned[:1].upper() + cleaned[1:]
    else:
        cleaned = f"Evaluated against top retrieved primary sources for \"{claim[:100]}\"."
    return f"Result : {title_verdict}, {cleaned}"


def _compute_analysis(evidence: list[dict], base_analysis: dict | None = None) -> dict:
    analysis = dict(base_analysis or {})
    supporting = [e for e in evidence if str(e.get("stance", "")).lower() == "supporting"]
    contradicting = [e for e in evidence if str(e.get("stance", "")).lower() == "contradicting"]
    domains = {
        (e.get("domain") or urlparse(str(e.get("source_url", ""))).netloc).lower().removeprefix("www.")
        for e in evidence
        if e.get("domain") or e.get("source_url")
    }
    domains.discard("")
    analysis["supporting_count"] = len(supporting)
    analysis["contradicting_count"] = len(contradicting)
    analysis["independent_domains"] = len(domains)
    return analysis


def _deterministic_resource_plan(claim_analysis: dict) -> dict:
    cat = str(claim_analysis.get("category") or claim_analysis.get("domain") or "").lower()
    domains = _DOMAIN_BY_CATEGORY.get(cat, [])
    return {"preferred_domains": domains} if domains else {}


async def investigate_async(text: str) -> InvestigationResponse:
    cache_key = " ".join(text.strip().lower().split())
    now = time.monotonic()
    cached = _INVESTIGATION_CACHE.get(cache_key)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    settings = get_settings()
    claim_analysis = ClaimIntelligence.analyze(text)
    use_ai = bool(settings.groq_api_key and settings.groq_api_key.strip())

    # 1. Zero-token deterministic claim decomposition, question framing & domain routing
    claims = decompose_claim(text)
    questions = QuestionService.frame(text, claim_analysis)[:2]
    resource_plan = _deterministic_resource_plan(claim_analysis)

    # 2. Concurrent multi-provider web search (top 5 high-authority sources)
    search_tasks = [search_web(q, max_results=5, resource_plan=resource_plan) for q in questions]
    batch_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    documents: list[dict] = []
    seen_urls: set[str] = set()
    docs_by_question: list[tuple[int, str, list[dict]]] = []

    for idx, (question, res) in enumerate(zip(questions, batch_results), start=1):
        if isinstance(res, Exception):
            logger.exception("Search failed for question %r: %s", question, res)
            docs = []
        else:
            docs = res[:3]
        docs_by_question.append((idx, question, docs))
        for doc in docs:
            url = doc.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                enriched = dict(doc)
                enriched["research_question"] = question
                documents.append(enriched)

    documents.sort(
        key=lambda x: (x.get("relevance_score", 0), x.get("source_quality", 0)),
        reverse=True,
    )
    documents = documents[:5]
    for i, doc in enumerate(documents, start=1):
        doc["evidence_id"] = f"E{i:02d}"

    # 3. Single-call Groq synthesis (saves ~85% daily token quota) with deterministic fallback
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

    # Propagate resolved publisher domains into evidence items
    doc_domain_by_url = {d.get("url"): d.get("domain", "") for d in documents if d.get("url")}
    for ev in evidence:
        if not ev.get("domain") and ev.get("source_url"):
            ev["domain"] = doc_domain_by_url.get(ev["source_url"], "")

    if llm_synthesis and llm_synthesis.get("verdict"):
        verdict_label = str(llm_synthesis["verdict"]).upper()
        try:
            confidence = max(0, min(100, int(round(float(llm_synthesis.get("confidence", 0))))))
        except (TypeError, ValueError):
            confidence = 50
        explanation = _format_quick_report(verdict_label, text, str(llm_synthesis.get("explanation") or ""))
        raw_analysis = llm_synthesis.get("analysis") if isinstance(llm_synthesis.get("analysis"), dict) else {}
        evidence_analysis = _compute_analysis(evidence, raw_analysis)
    else:
        verdict_data = VerdictService().evaluate(text, evidence)
        verdict_label = verdict_data["verdict"]
        confidence = verdict_data["confidence"]
        explanation = _format_quick_report(verdict_label, text, verdict_data["explanation"])
        evidence_analysis = _compute_analysis(evidence, verdict_data["analysis"])

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

    response = InvestigationResponse(
        claim=text,
        claims=claims,
        verdict=verdict_label,
        confidence=confidence,
        explanation=explanation,
        evidence=evidence,
        sources=researcher.normalize(documents),
        status="complete" if documents else "no_results",
        methodology=[
            "Deterministic atomic claim decomposition & domain routing",
            "Top-5 authoritative source retrieval (PubMed, Google News RSS, Wikipedia, DDGS)",
            "Single-pass closed-book AI synthesis with TTL response caching",
        ],
        claim_analysis=claim_analysis,
        evidence_analysis=evidence_analysis,
        research_questions=question_models,
    )

    if documents:
        if len(_INVESTIGATION_CACHE) >= 200:
            _INVESTIGATION_CACHE.pop(next(iter(_INVESTIGATION_CACHE)))
        _INVESTIGATION_CACHE[cache_key] = (now, response)

    return response


def investigate(text: str) -> InvestigationResponse:
    return asyncio.run(investigate_async(text))
