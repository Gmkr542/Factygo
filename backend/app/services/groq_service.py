from __future__ import annotations

import asyncio
import json
import logging
import re
import time

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the verification and synthesis engine for Factygo, a neutral evidence-first fact-checking platform. Use retrieved evidence and verified symbolic/math computations for factual conclusions. Never invent sources, URLs, quotations, statistics, or evidence IDs. Return ONLY valid JSON."""

_model_cache: tuple[float, set[str]] | None = None
MODEL_CACHE_SECONDS = 300
_ai_tokens_reset_at = 0.0


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
                kind = "tpd" if re.search(r"tokens? per day|\bTPD\b|daily token", msg, re.I) else "tpm"
                raise GroqRateLimitError(
                    f"AI analysis rate-limited. Retry in ~{max(1, round(retry_after))}s.",
                    retry_after=retry_after,
                    limit_kind=kind,
                )
            if r.status_code == 400 and "reduce the length" in r.text.lower():
                raise GroqPayloadTooLargeError("Prompt exceeded model context length.")
            r.raise_for_status()

        data = r.json()
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
        "HYBRID ENCYCLOPEDIC MODE: This is a settled scientific/physical fundamental claim. Anchor your verdict in the retrieved evidence (E01..E05) AND verified textbook physics/astronomy principles (e.g. Rayleigh scattering, optics) when snippets are brief, citing retrieved sources wherever applicable."
        if knowledge_mode == "hybrid_encyclopedic"
        else "STRICT CLOSED-BOOK MODE: Base your verdict strictly on the retrieved evidence (E01..E05) and deterministic COMPUTED FACTS below. If evidence is insufficient, return UNVERIFIED."
    )

    prompt = f"""Evaluate the claim using the evidence and verified deterministic computations below. Never invent sources, URLs, or quotes.
CLAIM: {claim!r}
SUB-CLAIMS TO CHECK: {json.dumps(subclaims, ensure_ascii=False)}
RESEARCH QUESTIONS: {json.dumps(questions, ensure_ascii=False)}
DETERMINISTIC COMPUTED FACTS (Ground-truth math & temporal logic):
{json.dumps(computed_facts or [], ensure_ascii=False)}
RETRIEVED EVIDENCE:
{json.dumps(compact, ensure_ascii=False)}

{grounding_rule}

Rules:
1. Choose overall verdict from: TRUE, MOSTLY TRUE, PARTLY TRUE, MISLEADING, MOSTLY FALSE, FALSE, UNVERIFIED.
2. Compute integer confidence (0-100) based on evidence quality, directness, and independent corroboration.
3. Write "explanation" in 1-2 short, direct sentences (under 55 words total) starting strictly with:
   Result : <Title-case Verdict>, <direct factual statement answering or correcting the claim immediately with specific scientific/technical facts and inline evidence IDs like (E01)>.
   - NEVER use filler phrases like "The claim that...", "Multiple sources indicate...", "Available evidence shows...", or "making the claim false". State the facts directly.
4. Evaluate each sub-claim in SUB-CLAIMS TO CHECK inside "claim_verdicts" with verdict ("TRUE"|"FALSE"|"PARTLY TRUE"|"UNVERIFIED") and evidence_id ("E01" or "").
5. For each evidence item you use, classify stance as "supporting", "contradicting", or "contextual" with a concise 1-sentence reason and strength (0.0 to 1.0).
6. Provide a concise answer for each research question grounded strictly in the evidence IDs.

Return ONLY valid JSON:
{{
  "verdict": "TRUE|MOSTLY TRUE|PARTLY TRUE|MISLEADING|MOSTLY FALSE|FALSE|UNVERIFIED",
  "confidence": 0,
  "explanation": "Result : False, ...",
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
