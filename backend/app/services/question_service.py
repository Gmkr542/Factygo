from __future__ import annotations

import re


class QuestionService:
    """Generates balanced support + adversarial counter-evidence queries to eliminate sycophancy."""

    @classmethod
    def frame(cls, claim: str, claim_analysis: dict | None = None) -> list[str]:
        text = re.sub(r"\s+", " ", claim).strip()
        analysis = claim_analysis or {}
        domain = analysis.get("domain", "general")

        if domain == "health_science":
            questions = [
                f"{text} clinical trial meta-analysis evidence",
                f"{text} limitations side effects OR no evidence",
            ]
        elif domain == "settled_science":
            questions = [
                text,
                f"{text} scientific explanation physics",
            ]
        elif domain == "indian_union_politics":
            questions = [
                f"{text} official government record",
                "Which party or coalition currently forms the Union Government of India?",
                f"{text} Lok Sabha election results",
            ]
        else:
            questions = [
                text,
                f"{text} limitations OR debunked OR counter evidence",
            ]

        result: list[str] = []
        seen: set[str] = set()
        for q in questions:
            cleaned = " ".join(q.split()).strip()
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                result.append(cleaned)
        return result[:3]
