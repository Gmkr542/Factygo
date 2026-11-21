from __future__ import annotations

import re
from datetime import datetime, timezone


class ClaimIntelligence:
    UNION_TERMS = {
        "centre", "center", "central government", "union government", "government of india",
        "national government", "central govt", "union govt", "lok sabha",
    }
    HEALTH_TERMS = {
        "cholesterol", "blood pressure", "diabetes", "cancer", "vaccine", "vitamin",
        "lemon", "garlic", "turmeric", "cure", "treats", "prevents", "symptom", "clinical",
        "insulin", "fasting", "antibiotics", "viral", "heart disease", "tea",
    }
    SETTLED_SCIENCE_TERMS = {
        "moon", "sun", "earth", "gravity", "rayleigh", "scattering", "solar", "cloudy",
        "boiling", "water", "photosynthesis", "speed of light", "great wall", "visible from",
        "planet", "atmosphere", "electricity", "physics", "chemistry", "astronomy",
    }
    FINANCE_TERMS = {
        "inflation", "gdp", "rbi", "interest rate", "stock", "tax", "budget", "recession", "population",
    }

    @classmethod
    def analyze(cls, claim: str) -> dict:
        text = re.sub(r"\s+", " ", claim).strip()
        lower = text.lower()
        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", lower)
        year = int(year_match.group(1)) if year_match else None
        if not year and any(x in lower for x in ("current", "today", "now", "latest")):
            year = datetime.now(timezone.utc).year

        if any(t in lower for t in cls.HEALTH_TERMS):
            domain = "health_science"
        elif any(t in lower for t in cls.SETTLED_SCIENCE_TERMS):
            domain = "settled_science"
        elif any(t in lower for t in cls.FINANCE_TERMS):
            domain = "economics_demographics"
        elif any(t in lower for t in cls.UNION_TERMS):
            domain = "indian_union_politics"
        else:
            domain = "general"

        # Hybrid routing mode: settled fundamentals allow encyclopedic scientific principles alongside retrieved sources
        knowledge_mode = (
            "hybrid_encyclopedic"
            if domain == "settled_science" and not year
            else "strict_closed_book"
        )

        jurisdiction = "UNION" if any(t in lower for t in cls.UNION_TERMS) else "GLOBAL"
        return {
            "normalized": text,
            "domain": domain,
            "knowledge_mode": knowledge_mode,
            "jurisdiction": jurisdiction,
            "year": year,
            "is_question": text.endswith("?") or bool(re.match(r"^(is|are|was|were|does|do|did|can|who|what|when|where|why|how)\b", lower)),
        }
