from __future__ import annotations

import re
from datetime import datetime, timezone


class ClaimIntelligence:
    """Deterministic claim normalization used alongside LLM decomposition."""

    UNION_TERMS = {
        "centre", "center", "central government", "union government", "government of india",
        "national government", "central govt", "union govt", "lok sabha",
    }
    HEALTH_TERMS = {
        "cholesterol", "blood pressure", "diabetes", "cancer", "vaccine", "vitamin",
        "lemon", "garlic", "turmeric", "cure", "treats", "prevents", "symptom", "clinical",
    }
    FINANCE_TERMS = {
        "inflation", "gdp", "rbi", "interest rate", "stock", "tax", "budget", "recession",
    }

    @classmethod
    def analyze(cls, claim: str) -> dict:
        text = re.sub(r"\s+", " ", claim).strip()
        lower = text.lower()
        year_match = re.search(r"\b(20\d{2})\b", lower)
        year = int(year_match.group(1)) if year_match else None
        if not year and any(x in lower for x in ("current", "today", "now", "latest")):
            year = datetime.now(timezone.utc).year

        if any(t in lower for t in cls.HEALTH_TERMS):
            domain = "health_science"
        elif any(t in lower for t in cls.FINANCE_TERMS):
            domain = "economics_finance"
        elif any(t in lower for t in cls.UNION_TERMS):
            domain = "indian_union_politics"
        else:
            domain = "general"

        jurisdiction = "UNION" if any(t in lower for t in cls.UNION_TERMS) else "GLOBAL"
        return {
            "normalized": text,
            "domain": domain,
            "jurisdiction": jurisdiction,
            "year": year,
            "is_question": text.endswith("?") or bool(re.match(r"^(is|are|was|were|does|do|did|can|who|what|when|where|why|how)\b", lower)),
        }
