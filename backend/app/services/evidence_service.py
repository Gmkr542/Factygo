from __future__ import annotations

import re


class EvidenceService:
    """Extract claim-relevant sentences from retrieved pages.

    This layer does not invent facts. It only returns text that actually exists
    in retrieved documents; semantic verdicting remains a separate layer.
    """

    def extract(self, documents: list[dict], claim: str) -> list[dict]:
        terms = [t.lower() for t in re.findall(r"[a-zA-Z0-9]{3,}", claim) if t.lower() not in {
            "the", "and", "for", "with", "that", "this", "from", "into", "about"
        }]
        evidence = []

        for doc in documents:
            text = doc.get("text", "")
            sentences = re.split(r"(?<=[.!?])\s+", text)
            candidates = []
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) < 50:
                    continue
                lower = sentence.lower()
                hits = sum(1 for term in terms if term in lower)
                if hits:
                    relevance = min(1.0, hits / max(2, len(terms)) + 0.2)
                    candidates.append((relevance, sentence))

            for relevance, sentence in sorted(candidates, reverse=True)[:2]:
                evidence.append({
                    "source_title": doc.get("title", "Untitled"),
                    "source_url": doc.get("url", ""),
                    "excerpt": sentence[:1200],
                    "stance": self._stance(sentence, claim),
                    "relevance": round(relevance, 3),
                    "source_score": float(doc.get("source_score", 0)),
                })

        evidence.sort(key=lambda x: (x["relevance"], x["source_score"]), reverse=True)
        return evidence[:10]

    @staticmethod
    def _stance(sentence: str, claim: str) -> str:
        # Conservative: keyword overlap alone cannot prove truth or falsity.
        # Mark as contextual unless explicit negation language is present.
        lower = sentence.lower()
        negations = ("not ", "no ", "never ", "false", "denied", "rejects", "did not", "does not")
        return "contradicting" if any(n in lower for n in negations) else "contextual"
