from __future__ import annotations

import asyncio
import logging
import re
import time
from urllib.parse import urlparse

from app.core.config import get_settings
from app.schemas.investigation import InvestigationResponse, ResearchQuestion
from app.services.article_parser import fetch_article
from app.services.citation_auditor import CitationAuditor
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


def _sanitize_visual_blocks(raw_blocks) -> list[dict]:
    if not isinstance(raw_blocks, list):
        return []
    clean_blocks: list[dict] = []
    for blk in raw_blocks[:3]:
        if not isinstance(blk, dict):
            continue
        btype = str(blk.get("type", "")).lower().strip()
        title = str(blk.get("title", "")).strip()[:120]
        if btype == "table":
            headers = [str(h).strip()[:60] for h in blk.get("headers", []) if str(h).strip()][:5]
            rows = []
            for r in blk.get("rows", [])[:6]:
                if isinstance(r, list) and any(str(c).strip() for c in r):
                    rows.append([str(c).strip()[:180] for c in r[:len(headers) or 5]])
            if headers and rows:
                clean_blocks.append({"type": "table", "title": title or "Comparison", "headers": headers, "rows": rows})
        elif btype == "timeline":
            events = []
            for ev in blk.get("events", [])[:6]:
                if isinstance(ev, dict) and str(ev.get("label", "")).strip():
                    events.append({
                        "date": str(ev.get("date", "")).strip()[:40],
                        "label": str(ev.get("label", "")).strip()[:200],
                        "evidence_id": str(ev.get("evidence_id", "")).strip()[:10],
                    })
            if len(events) >= 2:
                clean_blocks.append({"type": "timeline", "title": title or "Timeline", "events": events})
        elif btype == "bar_chart":
            bars = []
            for bar in blk.get("bars", [])[:6]:
                if isinstance(bar, dict) and str(bar.get("label", "")).strip():
                    try:
                        val = float(bar.get("value", 0))
                    except (TypeError, ValueError):
                        continue
                    bars.append({
                        "label": str(bar.get("label", "")).strip()[:60],
                        "value": max(0.0, val),
                        "display": str(bar.get("display", f"{val:g}")).strip()[:30],
                        "evidence_id": str(bar.get("evidence_id", "")).strip()[:10],
                    })
            if len(bars) >= 2:
                clean_blocks.append({
                    "type": "bar_chart",
                    "title": title or "Quantitative Breakdown",
                    "unit": str(blk.get("unit", "")).strip()[:16],
                    "bars": bars,
                })
    return clean_blocks


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


async def _enrich_top_articles(documents: list[dict]) -> None:
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


async def investigate_async(text: str, mode: str = "auto") -> InvestigationResponse:
    cache_key = f"{mode}:{' '.join(text.strip().lower().split())}"
    now = time.monotonic()
    cached = _INVESTIGATION_CACHE.get(cache_key)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    settings = get_settings()
    claim_analysis = ClaimIntelligence.analyze(text)
    use_ai = bool(settings.groq_api_key and settings.groq_api_key.strip())

    # Detect if input contains explicit DOIs, PMIDs, arXiv IDs, or URLs to audit
    detected_cits = CitationAuditor.detect_citations(text)
    has_citations = any(detected_cits.values())
    resolved_mode = "audit_ai" if (mode == "audit_ai" or (mode == "auto" and has_citations)) else "claim"

    claims = decompose_claim(text)
    subclaim_texts = [c.text for c in claims]
    questions = QuestionService.frame(text, claim_analysis)[:2]
    resource_plan = _deterministic_resource_plan(claim_analysis)

    # Run Citation/DOI Audit concurrently with multi-provider web retrieval
    audit_task = CitationAuditor.audit_text(text) if has_citations else asyncio.sleep(0, result=[])
    search_tasks = [search_web(q, max_results=5, resource_plan=resource_plan) for q in questions]
    gathered = await asyncio.gather(audit_task, *search_tasks, return_exceptions=True)

    citation_audits = gathered[0] if isinstance(gathered[0], list) else []
    batch_results = gathered[1:]

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

    # Confidence-Triggered Iterative Search: if top relevance is weak (<55), run a focused keyword pass
    top_rel = max((d.get("relevance_score", 0) for d in documents), default=0)
    if len(documents) < 2 or top_rel < 55:
        retry_q = f"{claim_analysis.get('subject', '')} {text[:90]}".strip()
        try:
            retry_docs = await search_web(retry_q, max_results=4)
            for doc in retry_docs:
                url = doc.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    enriched = dict(doc)
                    enriched["research_question"] = retry_q
                    documents.append(enriched)
        except Exception:
            pass

    documents.sort(
        key=lambda x: (x.get("relevance_score", 0), x.get("source_quality", 0)),
        reverse=True,
    )
    documents = documents[:5]
    for i, doc in enumerate(documents, start=1):
        doc["evidence_id"] = f"E{i:02d}"

    await _enrich_top_articles(documents)
    computed_facts = LogicService.analyze(text, documents)

    llm_synthesis: dict = {}
    if use_ai and (documents or citation_audits):
        try:
            llm_synthesis = await synthesize_investigation(
                text,
                subclaims=subclaim_texts,
                questions=questions,
                evidence_pool=documents,
                computed_facts=computed_facts,
                citation_audits=citation_audits,
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
    key_takeaways: list[str] = []
    caveat = ""
    visual_blocks: list[dict] = []

    if llm_synthesis and llm_synthesis.get("verdict"):
        verdict_label = str(llm_synthesis["verdict"]).upper()
        try:
            confidence = max(0, min(100, int(round(float(llm_synthesis.get("confidence", 0))))))
        except (TypeError, ValueError):
            confidence = 50
        explanation = _format_quick_report(verdict_label, text, str(llm_synthesis.get("explanation") or ""))
        raw_analysis = llm_synthesis.get("analysis") if isinstance(llm_synthesis.get("analysis"), dict) else {}
        evidence_analysis = _compute_analysis(evidence, raw_analysis)

        raw_kt = llm_synthesis.get("key_takeaways")
        if isinstance(raw_kt, list):
            key_takeaways = [str(x).strip() for x in raw_kt if str(x).strip()][:3]
        caveat = str(llm_synthesis.get("caveat") or "").strip()[:240]
        visual_blocks = _sanitize_visual_blocks(llm_synthesis.get("visual_blocks"))

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
    elif citation_audits and any(a.get("status") == "HALLUCINATED" for a in citation_audits):
        verdict_label = "FALSE"
        confidence = 95
        bad = [a["identifier"] for a in citation_audits if a.get("status") == "HALLUCINATED"]
        explanation = _format_quick_report(
            verdict_label,
            text,
            f"Audited citations {', '.join(bad)} do not exist in CrossRef/PubMed/arXiv registries.",
        )
        evidence_analysis = _compute_analysis(evidence)
    else:
        verdict_data = VerdictService().evaluate(text, evidence)
        verdict_label = verdict_data["verdict"]
        confidence = verdict_data["confidence"]
        explanation = _format_quick_report(verdict_label, text, verdict_data["explanation"])
        evidence_analysis = _compute_analysis(evidence, verdict_data["analysis"])

    # Auto-inject Evidence Pyramid warning if health claim relies solely on Tier 3 (Preclinical/Animal) studies
    if not caveat and claim_analysis.get("domain") == "health_science" and evidence:
        ranks = [e.get("study_tier_rank", 4) for e in evidence]
        if 3 in ranks and 1 not in ranks and 2 not in ranks:
            caveat = "Retrieved scientific evidence relies on preclinical/animal studies rather than human randomized clinical trials."

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
        mode_used=resolved_mode,
        claims=claims,
        claim_verdicts=claim_verdicts,
        computed_facts=computed_facts,
        citation_audits=citation_audits,
        verdict=verdict_label,
        confidence=confidence,
        explanation=explanation,
        key_takeaways=key_takeaways,
        caveat=caveat,
        visual_blocks=visual_blocks,
        evidence=evidence,
        sources=researcher.normalize(documents),
        status="complete" if (documents or citation_audits) else "no_results",
        methodology=[
            "Atomic sub-claim decomposition & adversarial support/counter-evidence query split",
            "Concurrent multi-provider retrieval (PubMed, Wikipedia, Google News RSS, DDGS) with syndication deduplication",
            "Live DOI / PubMed / arXiv / URL citation hallucination audit",
            "SSRF-safe full-article deep reading & Evidence Pyramid tiering",
            "Deterministic symbolic math, unit normalization & temporal logic verification",
        ],
        claim_analysis=claim_analysis,
        evidence_analysis=evidence_analysis,
        research_questions=question_models,
    )

    if documents or citation_audits:
        if len(_INVESTIGATION_CACHE) >= 200:
            _INVESTIGATION_CACHE.pop(next(iter(_INVESTIGATION_CACHE)))
        _INVESTIGATION_CACHE[cache_key] = (now, response)

    return response


def investigate(text: str) -> InvestigationResponse:
    return asyncio.run(investigate_async(text))
