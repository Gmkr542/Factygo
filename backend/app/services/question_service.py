from __future__ import annotations

import re


class QuestionService:
    """Generate clean, search-engine-friendly fallback questions when LLM planning is unavailable."""

    @classmethod
    def frame(cls, claim: str, claim_analysis: dict | None = None) -> list[str]:
        text = re.sub(r"\s+", " ", claim).strip()
        analysis = claim_analysis or {}
        domain = analysis.get("domain", "general")

        if domain == "health_science":
            questions = [
                f"{text} clinical study evidence",
                f"{text} medical review research",
                f"does {text} scientific consensus",
            ]
        elif domain == "indian_union_politics":
            questions = [
                f"{text} official government record",
                "Which party or coalition currently forms the Union Government of India?",
                f"{text} news verification",
            ]
        else:
            questions = [
                text,
                f"{text} fact check evidence",
                f"{text} official report study",
            ]

        result: list[str] = []
        seen: set[str] = set()
        for q in questions:
            cleaned = " ".join(q.split()).strip()
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                result.append(cleaned)
        return result[:4]
