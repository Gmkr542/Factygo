from __future__ import annotations

import asyncio
import json
import logging
import re
import time

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the verification, citation-auditing, and synthesis engine for Factygo, an evidence-first fact-checking platform. Use retrieved evidence, verified DOI/PubMed checks, and deterministic symbolic/math computations for factual conclusions. Never invent sources, URLs, numbers, or quotes. Return ONLY valid JSON."""

_model_cache: tuple[float, set[str]] | None = None
MODEL_CACHE_SECONDS = 300
_ai_tokens_reset_at = 0.0

_MODEL_DAILY_CAPS: dict[str, tuple[int, int]] = {
    "openai/gpt-oss-120b": (200_000, 1_000),
    "openai/gpt-oss-20b": (200_000, 1_000),
    "llama-3.3-70b-versatile": (100_000, 1_000),
    "llama-3.1-8b-instant": (500_000, 14_400),
}

_QUOTA_STATE: dict = {
    "remaining_tokens_tpm": None,
    "limit_tokens_tpm": None,
    "remaining_requests_rpd": None,
    "limit_requests_rpd": None,
    "reset_tokens_in": 0.0,
    "reset_requests_in": 0.0,
    "updated_at": 0.0,
    "model": None,
    "last_status": "idle",
}


def _daily_db_conn():
    import os
    import sqlite3
    s = get_settings()
    db_path = s.database_url.replace("sqlite:///", "") if s.database_url.startswith("sqlite:///") else "factygo.db"
    try:
        conn = sqlite3.connect(db_path)
    except Exception:
        conn = sqlite3.connect(os.path.join("/tmp", "factygo.db"))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_quota_usage (
            utc_date TEXT PRIMARY KEY,
            tokens_used INTEGER NOT NULL DEFAULT 0,
            requests_used INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    return conn


def _utc_today() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _record_daily_usage(tokens_delta: int, requests_delta: int = 1) -> None:
    try:
        today = _utc_today()
        conn = _daily_db_conn()
        with conn:
            conn.execute(
                """
                INSERT INTO daily_quota_usage (utc_date, tokens_used, requests_used)
                VALUES (?, ?, ?)
                ON CONFLICT(utc_date) DO UPDATE SET
                    tokens_used = tokens_used + excluded.tokens_used,
                    requests_used = requests_used + excluded.requests_used
                """,
                (today, max(0, int(tokens_delta)), max(0, int(requests_delta))),
            )
        conn.close()
    except Exception as exc:
        logger.debug("Daily quota DB update skipped: %s", exc)


def _get_daily_usage() -> tuple[int, int]:
    try:
        today = _utc_today()
        conn = _daily_db_conn()
        row = conn.execute(
            "SELECT tokens_used, requests_used FROM daily_quota_usage WHERE utc_date = ?",
            (today,),
        ).fetchone()
        conn.close()
        if row:
            return int(row[0]), int(row[1])
    except Exception:
        pass
    return 0, 0


def get_quota_status() -> dict:
    s = get_settings()
    now = time.monotonic()
    elapsed = (now - _QUOTA_STATE["updated_at"]) if _QUOTA_STATE["updated_at"] else 0.0
    active_model = _QUOTA_STATE["model"] or s.groq_model
    default_tpd, default_rpd = _MODEL_DAILY_CAPS.get(active_model, (200_000, 1_000))

    tokens_used_today, requests_used_today = _get_daily_usage()

    # Groq's x-ratelimit-remaining-requests / limit-requests reflects RPD (Requests Per Day)
    lim_rpd = _QUOTA_STATE["limit_requests_rpd"] or default_rpd
    rem_rpd = (
        _QUOTA_STATE["remaining_requests_rpd"]
        if _QUOTA_STATE["remaining_requests_rpd"] is not None
        else max(0, lim_rpd - requests_used_today)
    )
    rpd_pct = round((rem_rpd / lim_rpd) * 100) if lim_rpd > 0 else 100

    # Daily Token Budget (TPD) tracked persistently in SQLite
    lim_tpd = default_tpd
    rem_tpd = max(0, lim_tpd - tokens_used_today)
    tpd_pct = round((rem_tpd / lim_tpd) * 100) if lim_tpd > 0 else 100

    # Effective Daily Quota is the stricter of RPD% and TPD%
    daily_pct = max(0, min(100, min(rpd_pct, tpd_pct))) if s.groq_api_key else 0

    # TPM (Tokens Per Minute) from Groq's per-minute token header
    rem_tpm = _QUOTA_STATE["remaining_tokens_tpm"]
    lim_tpm = _QUOTA_STATE["limit_tokens_tpm"]
    tpm_pct = 100
    if lim_tpm and rem_tpm is not None and lim_tpm > 0:
        tpm_pct = round((rem_tpm / lim_tpm) * 100)
        if _QUOTA_STATE["reset_tokens_in"] > 0 and elapsed >= _QUOTA_STATE["reset_tokens_in"]:
            tpm_pct = 100
    elif not s.groq_api_key:
        tpm_pct = 0

    alert_level = "none"
    alert_message = ""
    if s.groq_api_key:
        if daily_pct <= 10 or _QUOTA_STATE["last_status"] == "tpd_limited":
            alert_level = "critical"
            alert_message = f"Critical: Daily AI quota is at {daily_pct}% ({rem_rpd} RPD / {rem_tpd:,} TPD left). Only run cached queries until 00:00 UTC reset."
        elif daily_pct <= 25:
            alert_level = "warning"
            alert_message = f"Low Daily Quota Alert: {daily_pct}% remaining ({rem_rpd}/{lim_rpd} requests left today). Repeated queries use cached results (0 quota)."

    from datetime import datetime, timezone, timedelta
    now_utc = datetime.now(timezone.utc)
    next_midnight_utc = (now_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    mins_until_reset = max(1, int((next_midnight_utc - now_utc).total_seconds() // 60))
    rpd_used_pct = max(0, min(100, 100 - int(rpd_pct))) if s.groq_api_key else 100
    rpd_limit_reached = bool(s.groq_api_key and (rem_rpd <= 0 or _QUOTA_STATE["last_status"] == "tpd_limited"))
    reset_time_str = next_midnight_utc.strftime("%H:%M UTC")
    if rpd_limit_reached and not alert_message:
        alert_level = "critical"
        alert_message = f"Daily RPD limit reached · Resets at {reset_time_str} ({mins_until_reset} min)."

    return {
        "ai_configured": bool(s.groq_api_key),
        "available_pct": daily_pct,
        "daily_available_pct": daily_pct,
        "rpd_available_pct": max(0, min(100, int(rpd_pct))),
        "rpd_used_pct": rpd_used_pct,
        "tpd_available_pct": max(0, min(100, int(tpd_pct))),
        "tpm_available_pct": max(0, min(100, int(tpm_pct))),
        "remaining_requests_rpd": rem_rpd,
        "limit_requests_rpd": lim_rpd,
        "remaining_tokens_tpd": rem_tpd,
        "limit_tokens_tpd": lim_tpd,
        "tokens_used_today": tokens_used_today,
        "remaining_tokens_tpm": rem_tpm,
        "limit_tokens_tpm": lim_tpm,
        "utc_date": _utc_today(),
        "reset_time_utc": reset_time_str,
        "reset_in_minutes": mins_until_reset,
        "rpd_limit_reached": rpd_limit_reached,
        "model": active_model,
        "alert_level": alert_level,
        "alert_message": alert_message,
        "status": "unconfigured" if not s.groq_api_key else _QUOTA_STATE["last_status"],
    }


def _record_rate_headers(headers, model: str, status_code: int, is_tpd: bool = False) -> None:
    def _int_hdr(name: str) -> int | None:
        val = headers.get(name)
        if val is None:
            return None
        try:
            return int(float(str(val).strip()))
        except ValueError:
            return None

    rem_tpm = _int_hdr("x-ratelimit-remaining-tokens")
    lim_tpm = _int_hdr("x-ratelimit-limit-tokens")
    rem_rpd = _int_hdr("x-ratelimit-remaining-requests")
    lim_rpd = _int_hdr("x-ratelimit-limit-requests")
    res_tok = _duration_seconds(headers.get("x-ratelimit-reset-tokens")) or 0.0
    res_req = _duration_seconds(headers.get("x-ratelimit-reset-requests")) or 0.0

    if rem_tpm is not None:
        _QUOTA_STATE["remaining_tokens_tpm"] = rem_tpm
    if lim_tpm is not None:
        _QUOTA_STATE["limit_tokens_tpm"] = lim_tpm
    if rem_rpd is not None:
        _QUOTA_STATE["remaining_requests_rpd"] = rem_rpd
    if lim_rpd is not None:
        _QUOTA_STATE["limit_requests_rpd"] = lim_rpd
    _QUOTA_STATE["reset_tokens_in"] = res_tok
    _QUOTA_STATE["reset_requests_in"] = res_req
    _QUOTA_STATE["updated_at"] = time.monotonic()
    _QUOTA_STATE["model"] = model
    if is_tpd:
        _QUOTA_STATE["last_status"] = "tpd_limited"
    else:
        _QUOTA_STATE["last_status"] = "rate_limited" if status_code == 429 else ("ok" if status_code < 400 else "error")


class GroqProviderError(RuntimeError):
    pass


class GroqPayloadTooLargeError(GroqProviderError):
    pass


class GroqRateLimitError(GroqProviderError):
    def __init__(self, message: str, retry_after: float = 10.0, limit_kind: str = "unknown"):
        super().__init__(message)
        self.retry_after = max(1.0, float(retry_after))
        self.limit_kind = limit_kind


def _duration_seconds(value: str | None) -> float | None:
    if not value:
        return None
    raw = str(value).strip().lower()
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    total = 0.0
    matches = list(re.finditer(r"(\d+(?:\.\d+)?)\s*(ms|h|m|s)", raw))
    if not matches:
        return None
    for m in matches:
        amt = float(m.group(1))
        unit = m.group(2)
        total += amt / 1000 if unit == "ms" else amt * {"s": 1, "m": 60, "h": 3600}[unit]
    return total


def _retry_delay_from_message(message: str, fallback: float) -> float:
    match = re.search(
        r"try again in\s+([0-9.]+\s*(?:ms|h|m|s)(?:\s*[0-9.]+\s*(?:ms|h|m|s))*)",
        str(message or ""),
        flags=re.I,
    )
    if match:
        parsed = _duration_seconds(match.group(1))
        if parsed is not None:
            return max(0.5, parsed)
    return max(0.5, float(fallback))


def _is_text_generation_model(model: str) -> bool:
    m = model.lower()
    blocked = ("prompt-guard", "guard", "safeguard", "moderation", "whisper", "tts", "embed", "rerank")
    if any(x in m for x in blocked):
        return False
    return any(x in m for x in ("gpt-oss", "llama-3", "llama-4", "qwen", "mixtral", "gemma"))


def _text_model_candidates(models: set[str]) -> list[str]:
    def score(model: str) -> tuple[int, str]:
        m = model.lower()
        if "gpt-oss" in m:
            rank = 0
        elif "llama-3.3" in m:
            rank = 1
        elif "llama-3" in m:
            rank = 2
        elif "qwen" in m:
            rank = 3
        elif "llama-4" in m:
            rank = 4
        else:
            rank = 5
        return rank, m

    return sorted((m for m in models if _is_text_generation_model(m)), key=score)


async def _available_models() -> set[str]:
    global _model_cache
    now = time.monotonic()
    if _model_cache and now - _model_cache[0] < MODEL_CACHE_SECONDS:
        return _model_cache[1]
    s = get_settings()
    async with httpx.AsyncClient(timeout=min(s.request_timeout, 15)) as c:
        r = await c.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {s.groq_api_key}"},
        )
        r.raise_for_status()
        data = r.json()
    models = {str(x.get("id")) for x in data.get("data", []) if isinstance(x, dict) and x.get("id")}
    _model_cache = (now, models)
    return models


async def _request_impl(model: str, instruction: str) -> str:
    global _ai_tokens_reset_at
    s = get_settings()
    if len(instruction) > s.groq_max_instruction_chars:
        raise GroqPayloadTooLargeError("The research payload is too large for the AI analysis model.")

    async with httpx.AsyncClient(timeout=s.request_timeout) as c:
        r = await c.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {s.groq_api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": instruction},
                ],
            },
        )
        _record_rate_headers(r.headers, model, r.status_code)
        reset_sec = _duration_seconds(r.headers.get("x-ratelimit-reset-tokens"))
        if reset_sec is not None:
            _ai_tokens_reset_at = time.monotonic() + reset_sec

        if r.is_error:
            logger.error("Groq error: status=%s model=%s body=%s", r.status_code, model, r.text[:600])
            if r.status_code == 429:
                retry_after = 10.0
                if r.headers.get("Retry-After"):
                    try:
                        retry_after = float(r.headers["Retry-After"])
                    except ValueError:
                        pass
                try:
                    msg = str(r.json().get("error", {}).get("message", ""))
                except Exception:
                    msg = r.text
                retry_after = _retry_delay_from_message(msg, retry_after)
                kind = "tpd" if re.search(r"tokens? per day|requests? per day|\bTPD\b|\bRPD\b|daily", msg, re.I) else "tpm"
                if kind == "tpd":
                    _QUOTA_STATE["last_status"] = "tpd_limited"
                raise GroqRateLimitError(
                    f"AI analysis rate-limited. Retry in ~{max(1, round(retry_after))}s.",
                    retry_after=retry_after,
                    limit_kind=kind,
                )
            if r.status_code == 400 and "reduce the length" in r.text.lower():
                raise GroqPayloadTooLargeError("Prompt exceeded model context length.")
            r.raise_for_status()

        data = r.json()
        usage = data.get("usage") or {}
        _record_daily_usage(int(usage.get("total_tokens", 0)), 1)
        return data["choices"][0]["message"]["content"]


async def _request_bounded(model: str, instruction: str) -> str:
    s = get_settings()
    started = time.monotonic()
    while True:
        try:
            return await _request_impl(model, instruction)
        except GroqRateLimitError as e:
            now = time.monotonic()
            reset_in = max(0.0, _ai_tokens_reset_at - now)
            delay = reset_in if e.limit_kind == "tpm" and reset_in > 0 else e.retry_after
            if e.limit_kind == "tpd" or (now - started) + delay > s.max_ai_wait_seconds:
                raise
            logger.warning("Groq TPM pause for %.1fs on model=%s", delay, model)
            await asyncio.sleep(min(delay, 10.0))


def _parse_json(content: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON from Groq: %s", cleaned[:600])
        raise RuntimeError("AI returned invalid JSON") from e


async def groq_json(instruction: str) -> dict:
    s = get_settings()
    if not s.groq_api_key:
        raise GroqProviderError("GROQ_API_KEY is not configured")

    candidates = []
    for m in (s.groq_model, s.groq_fallback_model):
        if m and m not in candidates and m != "llama-3.3-70b-versatile":
            candidates.append(m)

    last_err = None
    for model in candidates:
        try:
            raw = await _request_bounded(model, instruction)
            return _parse_json(raw)
        except httpx.HTTPStatusError as e:
            last_err = e
            if e.response.status_code != 404:
                raise
            logger.warning("Configured model 404, trying fallback: %s", model)

    available = await _available_models()
    for model in _text_model_candidates(available):
        if model in candidates:
            continue
        try:
            raw = await _request_bounded(model, instruction)
            return _parse_json(raw)
        except httpx.HTTPStatusError as e:
            last_err = e
            if e.response.status_code == 404:
                continue
            raise

    raise GroqProviderError("No available Groq text model found.") from last_err


async def synthesize_investigation(
    claim: str,
    subclaims: list[str],
    questions: list[str],
    evidence_pool: list[dict],
    computed_facts: list[str] | None = None,
    citation_audits: list[dict] | None = None,
    knowledge_mode: str = "strict_closed_book",
) -> dict:
    compact = [
        {
            "evidence_id": item["evidence_id"],
            "title": item.get("title", "")[:200],
            "publisher": item.get("publisher", "")[:80],
            "url": item.get("url", ""),
            "source_type": item.get("source_type", "Web Source"),
            "source_quality": item.get("source_quality", 65),
            "full_article_read": bool(item.get("full_article_read", False)),
            "content": str(item.get("content", ""))[:1600],
        }
        for item in evidence_pool[:6]
    ]

    grounding_rule = (
        "HYBRID ENCYCLOPEDIC MODE: This is a settled scientific/physical fundamental claim. Anchor your verdict in retrieved evidence (E01..E05) AND verified textbook physics/astronomy principles (e.g. Rayleigh scattering, optics) when snippets are brief, citing retrieved sources wherever applicable."
        if knowledge_mode == "hybrid_encyclopedic"
        else "STRICT CLOSED-BOOK MODE: Base your verdict strictly on retrieved evidence (E01..E05), CITATION AUDIT RESULTS, and deterministic COMPUTED FACTS below. If evidence is insufficient, return UNVERIFIED."
    )

    prompt = f"""Evaluate the claim or AI-generated passage using the evidence, citation audit results, and deterministic computations below. Never invent sources, URLs, numbers, or quotes.
INPUT: {claim!r}
SUB-CLAIMS TO CHECK: {json.dumps(subclaims, ensure_ascii=False)}
RESEARCH QUESTIONS: {json.dumps(questions, ensure_ascii=False)}
CITATION & DOI AUDIT RESULTS:
{json.dumps(citation_audits or [], ensure_ascii=False)}
DETERMINISTIC COMPUTED FACTS:
{json.dumps(computed_facts or [], ensure_ascii=False)}
RETRIEVED EVIDENCE:
{json.dumps(compact, ensure_ascii=False)}

{grounding_rule}

Rules:
1. Choose overall verdict from: TRUE, MOSTLY TRUE, PARTLY TRUE, MISLEADING, MOSTLY FALSE, FALSE, UNVERIFIED. (If CITATION AUDIT RESULTS show HALLUCINATED DOIs/PMIDs, mark FALSE or MISLEADING).
2. Compute integer confidence (0-100) based on evidence quality, directness, and independent corroboration.
3. Write "explanation" in 1-2 short, direct sentences (under 50 words total) starting strictly with:
   Result : <Title-case Verdict>, <direct factual statement answering or correcting the claim immediately with specific scientific/technical facts and inline evidence IDs like (E01)>.
   - NEVER use filler phrases like "The claim that...", "Multiple sources indicate...", "Available evidence shows...", or "making the claim false". State the facts directly.
4. Provide 2-3 concise, high-signal "key_takeaways" (12-22 words each) summarizing concrete findings with evidence IDs like (E01).
5. Provide "caveat" (1 short sentence, or empty string "") ONLY if retrieved evidence has limitations (e.g., preliminary animal studies, missing exact figures, or regional scope).
6. CONTEXTUAL VISUAL BLOCK ("visual_blocks"): When the input asks to compare two things, spans multiple dates, or contains verified numeric ranges across categories, emit 1 structured visual block (otherwise return []):
   - Comparison table: {{"type": "table", "title": "string", "headers": ["Aspect", "Claimed", "Verified Evidence"], "rows": [["...", "...", "... (E01)"]]}}
   - Chronological timeline: {{"type": "timeline", "title": "string", "events": [{{"date": "2023", "label": "Event description", "evidence_id": "E01"}}]}}
   - Quantitative bar chart (ONLY when exact numbers appear in evidence/computed facts): {{"type": "bar_chart", "title": "string", "unit": "%", "bars": [{{"label": "Category", "value": 75, "display": "75%", "evidence_id": "E01"}}]}}
7. Evaluate each sub-claim in SUB-CLAIMS TO CHECK inside "claim_verdicts" with verdict ("TRUE"|"FALSE"|"PARTLY TRUE"|"UNVERIFIED") and evidence_id ("E01" or "").
8. For each evidence item you use, classify stance as "supporting", "contradicting", or "contextual" with a concise 1-sentence reason and strength (0.0 to 1.0).
9. Provide a concise answer for each research question grounded strictly in the evidence IDs.

Return ONLY valid JSON:
{{
  "verdict": "TRUE|MOSTLY TRUE|PARTLY TRUE|MISLEADING|MOSTLY FALSE|FALSE|UNVERIFIED",
  "confidence": 0,
  "explanation": "Result : False, ...",
  "key_takeaways": ["Concrete fact 1 (E01)", "Concrete fact 2 (E02)"],
  "caveat": "Optional limitation note or empty string",
  "visual_blocks": [],
  "claim_verdicts": [
    {{"subclaim": "string", "verdict": "TRUE|FALSE|PARTLY TRUE|UNVERIFIED", "evidence_id": "E01"}}
  ],
  "evidence_assessments": [
    {{"evidence_id": "E01", "stance": "supporting|contradicting|contextual", "strength": 0.85, "reason": "string"}}
  ],
  "question_answers": [
    {{"question": "string", "answer": "string", "evidence_ids": ["E01"]}}
  ],
  "analysis": {{
    "supporting_count": 0,
    "contradicting_count": 0,
    "independent_domains": 0,
    "limitations": "string"
  }}
}}"""
    return await groq_json(prompt)
