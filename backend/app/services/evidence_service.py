from __future__ import annotations

import re
from app.services.claim_intelligence import ClaimIntelligence


def classify_study_tier(title: str, text: str, source_type: str) -> tuple[str, int]:
    blob = f"{title} {text}".lower()
    if any(k in blob for k in ("systematic review", "meta-analysis", "randomized controlled trial", "randomised controlled trial", "double-blind", "cochrane")):
        return ("Tier 1 · Meta-Analysis / RCT", 1)
    if "government" in source_type.lower() or "official" in source_type.lower() or any(k in blob for k in ("clinical trial", "cohort study", "human trial", "clinical study", "who ", "cdc ", "nih ", "government", "official")):
        return ("Tier 2 · Clinical / Official", 2)
    if any(k in blob for k in ("in vitro", "in-vitro", "mice", "mouse", "rat model", "rodent", "animal study", "cell line", "preclinical")):
        return ("Tier 3 · Preclinical / Animal", 3)
    if "academic" in source_type.lower() or "reference" in source_type.lower():
        return ("Tier 2 · Reference / Study", 2)
    return ("Tier 4 · News / General Web", 4)


class EvidenceService:
    STOPWORDS = {
        "the", "and", "for", "with", "that", "this", "from", "into", "about",
        "is", "are", "in", "of", "to", "a", "an", "on", "was", "were", "does",
    }

    def extract(
        self,
        documents: list[dict],
        claim: str,
        llm_assessments: list[dict] | None = None,
    ) -> list[dict]:
        meta = ClaimIntelligence.analyze(claim)
        terms = self._terms(claim)
        assessment_map = {
            str(a.get("evidence_id", "")): a
            for a in (llm_assessments or [])
            if isinstance(a, dict) and a.get("evidence_id")
        }

        evidence: list[dict] = []
        for idx, doc in enumerate(documents, start=1):
            eid = doc.get("evidence_id") or f"E{idx:02d}"
            text = str(doc.get("content") or doc.get("text") or "").strip()
            title = str(doc.get("title") or "Untitled").strip()
            excerpt = self._best_excerpt(text, terms) or title
            relevance = self._relevance(f"{title} {excerpt}", terms)
            source_score = float(doc.get("source_score", doc.get("source_quality", 65) / 100.0))
            source_type = doc.get("source_type", "Web Source")
            study_tier_label, study_tier_num = classify_study_tier(title, excerpt, source_type)

            # Jurisdiction check (Union vs State)
            j_match = True
            if meta.get("jurisdiction") == "UNION":
                low_blob = f"{title} {excerpt}".lower()
                if any(st in low_blob for st in ClaimIntelligence.STATE_TERMS) and not any(
                    u in low_blob for u in ("prime minister", "lok sabha", "union government", "central government", "government of india", "nda")
                ):
                    j_match = False

            llm_item = assessment_map.get(eid)
            if llm_item:
                stance = str(llm_item.get("stance", "contextual")).lower()
                if stance not in {"supporting", "contradicting", "contextual"}:
                    stance = "contextual"
                strength = round(min(1.0, max(0.0, float(llm_item.get("strength", 0.6)))), 3)
                reason = str(llm_item.get("reason") or "Evaluated against the claim.").strip()
            else:
                if not j_match:
                    stance, reason = "contextual", "Passage describes state-level governance rather than the Union Government."
                else:
                    stance, reason = self._heuristic_stance(f"{title} {excerpt}".lower(), claim.lower())
                strength = round(min(1.0, relevance * 0.6 + source_score * 0.4), 3)

            evidence.append({
                "evidence_id": eid,
                "source_title": title,
                "publisher": doc.get("publisher", ""),
                "domain": doc.get("domain", ""),
                "source_url": doc.get("url", ""),
                "excerpt": excerpt[:1400],
                "stance": stance,
                "relevance": round(min(1.0, max(relevance, 0.25 if llm_item else relevance)), 3),
                "source_score": round(source_score, 2),
                "source_tier": doc.get("tier", 3),
                "source_type": source_type,
                "study_tier": study_tier_label,
                "study_tier_rank": study_tier_num,
                "full_article_read": bool(doc.get("full_article_read", False)),
                "jurisdiction_match": j_match,
                "temporal_match": self._time_match(f"{title} {excerpt}", meta.get("year")),
                "strength": strength,
                "reason": reason,
            })

        evidence.sort(key=lambda x: (x["strength"], x["relevance"], x["source_score"]), reverse=True)
        return evidence[:15]

    @classmethod
    def _terms(cls, text: str) -> list[str]:
        return [
            x.lower()
            for x in re.findall(r"[a-zA-Z0-9]+", text)
            if len(x) >= 3 and x.lower() not in cls.STOPWORDS
        ]

    @staticmethod
    def _relevance(passage: str, terms: list[str]) -> float:
        if not terms:
            return 0.5
        lower = passage.lower()
        hits = sum(1 for t in terms if t in lower)
        return min(1.0, hits / max(2, len(terms)) + (0.15 if hits >= 2 else 0.0))

    @classmethod
    def _best_excerpt(cls, text: str, terms: list[str]) -> str:
        if not text:
            return ""
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) >= 30]
        if not sentences:
            return text[:600]
        scored = sorted(sentences, key=lambda s: cls._relevance(s, terms), reverse=True)
        return " ".join(scored[:2])[:900]

    @staticmethod
    def _heuristic_stance(lower: str, claim_lower: str = "") -> tuple[str, str]:
        if "congress" in claim_lower and "prime minister" in lower and ("narendra modi" in lower or "bjp" in lower or "nda" in lower):
            return "contradicting", "Official record shows Narendra Modi (BJP/NDA) leads the Government of India."
        contra_cues = ("no evidence", "does not", "do not", "myth", "false", "unlikely", "insufficient evidence", "not proven", "contradict", "debunk", "overtake", "surpasses")
        support_cues = ("study shows", "clinical trial", "significantly reduced", "lowered cholesterol", "confirmed", "evidence shows", "found that")
        if any(c in lower for c in contra_cues):
            return "contradicting", "Passage contradicts or refutes the claim."
        if any(c in lower for c in support_cues):
            return "supporting", "Passage reports findings consistent with the claim."
        return "contextual", "Relevant source passage providing context on the topic."

    @staticmethod
    def _time_match(passage: str, year: int | None) -> bool:
        if not year:
            return True
        years = [int(x) for x in re.findall(r"\b20\d{2}\b", passage)]
        return not years or any(abs(y - year) <= 1 for y in years)
