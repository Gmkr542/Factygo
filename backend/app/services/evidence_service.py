from __future__ import annotations

import re
from urllib.parse import urlparse


_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "about",
    "there", "their", "they", "have", "has", "been", "were", "will", "would",
    "could", "should", "what", "when", "where", "which", "while", "than",
}

# Conservative lexical cues. This is intentionally transparent and deterministic;
# it is not presented as a substitute for an ML/LLM entailment model.
_SUPPORT_PATTERNS = (
    r"\b(?:is|are|was|were)\s+(?:a|an|the)?\s*(?:fact|true|correct|real|valid)\b",
    r"\b(?:confirmed|confirms|demonstrates|shows|establishes|proves|found|finds)\b",
    r"\b(?:evidence|research|study|studies|data)\s+(?:shows|finds|indicates|supports)\b",
    r"\bscientists?\s+(?:agree|have found|have shown)\b",
)
_CONTRADICT_PATTERNS = (
    r"\b(?:false|untrue|incorrect|wrong|myth|debunked|disproven|refuted)\b",
    r"\b(?:not|never|no)\s+(?:a\s+)?(?:fact|true|correct|real|valid)\b",
    r"\b(?:does|do|did|is|are|was|were)\s+not\b",
    r"\b(?:rejects?|denies?|contradicts?|refutes?|disproves?)\b",
    r"\b(?:instead|rather),?\s+(?:the\s+)?(?:earth|claim|statement)\b",
)


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[a-zA-Z0-9]{3,}", text)
        if token.lower() not in _STOPWORDS
    }


class EvidenceService:
    """Extract and classify claim-relevant evidence conservatively.

    The classifier combines lexical relevance, explicit stance cues and a small
    set of domain-aware patterns. It never claims that keyword overlap alone is
    proof; the verdict layer also requires source quality and corroboration.
    """

    def extract(self, documents: list[dict], claim: str) -> list[dict]:
        claim_terms = _tokens(claim)
        evidence: list[dict] = []

        for doc in documents:
            text = doc.get("text", "")
            sentences = self._sentences(text)
            candidates: list[tuple[float, str]] = []

            for sentence in sentences:
                sentence_terms = _tokens(sentence)
                overlap = len(claim_terms & sentence_terms)
                if overlap == 0:
                    continue

                relevance = min(1.0, overlap / max(1, min(len(claim_terms), 8)))
                if len(sentence_terms & claim_terms) >= 2:
                    relevance = min(1.0, relevance + 0.15)
                if len(sentence) > 120:
                    relevance = min(1.0, relevance + 0.05)
                candidates.append((relevance, sentence))

            for relevance, sentence in sorted(candidates, reverse=True)[:3]:
                stance, strength, rationale = self._classify(sentence, claim)
                domain = urlparse(doc.get("url", "")).netloc.lower().removeprefix("www.")
                evidence.append({
                    "source_title": doc.get("title", "Untitled"),
                    "source_url": doc.get("url", ""),
                    "excerpt": sentence[:1200],
                    "stance": stance,
                    "relevance": round(relevance, 3),
                    "source_score": float(doc.get("source_score", 0)),
                    "source_type": doc.get("source_type", "unknown"),
                    "source_tier": int(doc.get("source_tier", 5)),
                    "domain": domain,
                    "strength": round(strength, 3),
                    "rationale": rationale,
                })

        evidence.sort(
            key=lambda x: (x["strength"] * x["relevance"], x["source_score"]),
            reverse=True,
        )
        return evidence[:15]

    @staticmethod
    def _sentences(text: str) -> list[str]:
        text = re.sub(r"\s+", " ", text).strip()
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if 30 <= len(s.strip()) <= 1800]

    @staticmethod
    def _classify(sentence: str, claim: str) -> tuple[str, float, str]:
        lower = sentence.lower()
        support_hits = sum(bool(re.search(pattern, lower)) for pattern in _SUPPORT_PATTERNS)
        contradict_hits = sum(bool(re.search(pattern, lower)) for pattern in _CONTRADICT_PATTERNS)

        # Direct phrase/predicate matching is stronger than a generic cue.
        claim_norm = re.sub(r"[^a-z0-9 ]", " ", claim.lower())
        claim_norm = re.sub(r"\s+", " ", claim_norm).strip()
        direct = claim_norm and claim_norm in lower

        if contradict_hits > support_hits:
            strength = min(1.0, 0.55 + 0.15 * contradict_hits + (0.1 if direct else 0))
            return "contradicting", strength, "Explicit contradiction/negation cue in the retrieved passage."
        if support_hits > contradict_hits:
            strength = min(1.0, 0.55 + 0.15 * support_hits + (0.1 if direct else 0))
            return "supporting", strength, "Explicit support/confirmation cue in the retrieved passage."

        return "contextual", min(0.65, 0.35 + (0.1 if direct else 0)), "Relevant passage, but no sufficiently explicit support or contradiction cue."
