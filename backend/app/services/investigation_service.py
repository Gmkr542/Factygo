from __future__ import annotations

import asyncio
import logging
import re
import time
from urllib.parse import urlparse

from app.core.config import get_settings
from app.schemas.investigation import InvestigationResponse, ResearchQuestion
from app.services.article_parser import fetch_article
from app.services.claim_intelligence import ClaimIntelligence
from app.services.claim_service import decompose_claim
from app.services.evidence_service import EvidenceService
from app.services.groq_service import synthesize_investigation
from app.services.logic_service import LogicService
from app.services.question_service import QuestionService
from app.services.search_service import ResearchService, search_web
from app.services.verdict_service import VerdictService

logger = logging.getLogger(__name__)

_INVESTIGATION_CACHE: dict[str, tuple[float, InvestigationResponse]] = {}
_CACHE_TTL_SECONDS = 3600

_DOMAIN_BY_CATEGORY = {
    "health": ["pubmed.ncbi.nlm.nih.gov", "who.int", "nih.gov"],
    "health_science": ["pubmed.ncbi.nlm.nih.gov", "who.int", "nih.gov"],
    "medical": ["pubmed.ncbi.nlm.nih.gov", "who.int", "nih.gov"],
    "settled_science": ["en.wikipedia.org", "nasa.gov", "nature.com"],
    "science": ["nature.com", "pubmed.ncbi.nlm.nih.gov", "arxiv.org"],
    "finance": ["imf.org", "worldbank.org", "sec.gov"],
    "economics_demographics": ["un.org", "pewresearch.org", "worldbank.org"],
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


async def _enrich_top_articles(documents: list[dict], claim: str) -> None:
    """Upgrade #2: Deep-read the top 2 non-redirect HTML sources for full context & caveats."""
    targets = [
        doc for doc in documents[:3]
        if doc.get("url", "").startswith(("http://", "https://"))
        and "news.google.com/rss/" not in doc.get("url", "")
    ][:2]
    if not targets:
        return

    async def _fetch_one(doc: dict) -> None:
        try:
            _title, full_text = await asyncio.wait_for(
                fetch_article(doc["url"], timeout_override=5.0),
                timeout=6.0,
            )
            if full_text and len(full_text) > len(doc.get("content", "")):
                doc["content"] = full_text[:2800]
                doc["text"] = full_text[:2800]
                doc["full_article_read"] = True
        except Exception:
            pass

    await asyncio.gather(*[_fetch_one(d) for d in targets], return_exceptions=True)


async def investigate_async(text: str) -> InvestigationResponse:
    cache_key = " ".join(text.strip().lower().split())
    now = time.monotonic()
    cached = _INVESTIGATION_CACHE.get(cache_key)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    settings = get_settings()
    claim_analysis = ClaimIntelligence.analyze(text)
    use_ai = bool(settings.groq_api_key and settings.groq_api_key.strip())

    # 1. Deterministic atomic claim decomposition, question framing & hybrid routing
    claims = decompose_claim(text)
    subclaim_texts = [c.text for c in claims]
    questions = QuestionService.frame(text, claim_analysis)[:2]
    resource_plan = _deterministic_resource_plan(claim_analysis)

    # 2. Concurrent multi-provider web search (DDGS + Google News RSS + PubMed + Wikipedia)
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

    # 3. Full-Article Deep Reading (top 2 URLs) + Symbolic Math/Date Logic Verification
    await _enrich_top_articles(documents, text)
    computed_facts = LogicService.analyze(text, documents)

    # 4. Single-call Groq synthesis with deterministic fallback
    llm_synthesis: dict = {}
    if use_ai and documents:
        try:
            llm_synthesis = await synthesize_investigation(
                text,
                subclaims=subclaim_texts,
                questions=questions,
                evidence_pool=documents,
                computed_facts=computed_facts,
                knowledge_mode=claim_analysis.get("knowledge_mode", "strict_closed_book"),
            )
        except Exception as exc:
            logger.warning("LLM synthesis failed, falling back to deterministic verdict: %s", exc)

    evidence_service = EvidenceService()
    evidence = evidence_service.extract(
        documents,
        text,
        llm_assessments=llm_synthesis.get("evidence_assessments"),
    )

    doc_domain_by_url = {d.get("url"): d.get("domain", "") for d in documents if d.get("url")}
    for ev in evidence:
        if not ev.get("domain") and ev.get("source_url"):
            ev["domain"] = doc_domain_by_url.get(ev["source_url"], "")

    claim_verdicts: list[dict] = []
    if llm_synthesis and llm_synthesis.get("verdict"):
        verdict_label = str(llm_synthesis["verdict"]).upper()
        try:
            confidence = max(0, min(100, int(round(float(llm_synthesis.get("confidence", 0))))))
        except (TypeError, ValueError):
            confidence = 50
        explanation = _format_quick_report(verdict_label, text, str(llm_synthesis.get("explanation") or ""))
        raw_analysis = llm_synthesis.get("analysis") if isinstance(llm_synthesis.get("analysis"), dict) else {}
        evidence_analysis = _compute_analysis(evidence, raw_analysis)
        raw_cv = llm_synthesis.get("claim_verdicts")
        if isinstance(raw_cv, list):
            claim_verdicts = [
                {
                    "subclaim": str(x.get("subclaim", "")).strip(),
                    "verdict": str(x.get("verdict", "UNVERIFIED")).upper(),
                    "evidence_id": str(x.get("evidence_id", "")).strip(),
                }
                for x in raw_cv
                if isinstance(x, dict) and str(x.get("subclaim", "")).strip()
            ][:4]
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
        claim_verdicts=claim_verdicts,
        computed_facts=computed_facts,
        verdict=verdict_label,
        confidence=confidence,
        explanation=explanation,
        evidence=evidence,
        sources=researcher.normalize(documents),
        status="complete" if documents else "no_results",
        methodology=[
            "Atomic claim decomposition & hybrid knowledge-mode routing",
            "Concurrent multi-provider retrieval (PubMed, Wikipedia, Google News RSS, DDGS)",
            "SSRF-safe full-article deep reading for top authoritative sources",
            "Deterministic symbolic math & temporal logic verification",
            "Evidence-grounded AI synthesis with TTL caching",
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
