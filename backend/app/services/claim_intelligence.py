from __future__ import annotations

import re
from datetime import datetime, timezone


class ClaimIntelligence:
    UNION_TERMS = {
        "centre", "center", "central government", "union government", "government of india",
        "national government", "central govt", "union govt", "lok sabha", "prime minister of india",
    }
    STATE_TERMS = {
        "kerala", "tamil nadu", "karnataka", "maharashtra", "gujarat", "rajasthan",
        "west bengal", "uttar pradesh", "bihar", "andhra pradesh", "telangana", "delhi", "punjab",
    }
    HEALTH_TERMS = {
        "cholesterol", "blood pressure", "diabetes", "cancer", "vaccine", "vitamin",
        "lemon", "garlic", "turmeric", "cure", "treats", "prevents", "symptom", "clinical",
        "insulin", "fasting", "antibiotics", "viral", "heart disease", "tea", "rct", "study",
    }
    SETTLED_SCIENCE_TERMS = {
        "moon", "sun", "earth", "gravity", "rayleigh", "scattering", "solar", "cloudy",
        "boiling", "water", "photosynthesis", "speed of light", "great wall", "visible from",
        "planet", "atmosphere", "electricity", "physics", "chemistry", "astronomy", "orbits",
    }
    FINANCE_TERMS = {
        "inflation", "gdp", "rbi", "interest rate", "stock", "tax", "budget", "recession", "population",
    }

    @classmethod
    def analyze(cls, claim: str) -> dict:
        now = datetime.now(timezone.utc)
        text = re.sub(r"\s+", " ", claim).strip()
        lower = text.lower()
        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", lower)
        year = int(year_match.group(1)) if year_match else None
        if not year and any(x in lower for x in ("current", "today", "now", "latest")):
            year = now.year

        if any(t in lower for t in cls.HEALTH_TERMS):
            domain = "health_science"
            volatility = "Evolving Clinical Evidence"
        elif any(t in lower for t in cls.SETTLED_SCIENCE_TERMS):
            domain = "settled_science"
            volatility = "Immutable Physical Law"
        elif any(t in lower for t in cls.FINANCE_TERMS):
            domain = "economics_demographics"
            volatility = "Annual / Periodic Metric"
        elif any(t in lower for t in cls.UNION_TERMS):
            domain = "indian_union_politics"
            volatility = "Live Officeholder / Term"
        else:
            domain = "general"
            volatility = "Point-in-Time Fact"

        subject = "General"
        if "congress" in lower:
            subject = "Indian National Congress"
        elif "bjp" in lower or "nda" in lower:
            subject = "Bharatiya Janata Party / NDA"
        elif "india" in lower:
            subject = "India"
        elif "chandrayaan" in lower:
            subject = "Chandrayaan-3"
        elif "solar" in lower:
            subject = "Solar Energy"
        elif "moon" in lower:
            subject = "Moon"

        knowledge_mode = (
            "hybrid_encyclopedic"
            if domain == "settled_science" and not year
            else "strict_closed_book"
        )

        jurisdiction = "UNION" if any(t in lower for t in cls.UNION_TERMS) else "GLOBAL"
        valid_as_of = now.strftime("%b %Y")

        return {
            "normalized": text,
            "subject": subject,
            "domain": domain,
            "knowledge_mode": knowledge_mode,
            "jurisdiction": jurisdiction,
            "year": year,
            "volatility": volatility,
            "valid_as_of": valid_as_of,
            "is_question": text.endswith("?") or bool(re.match(r"^(is|are|was|were|does|do|did|can|who|what|when|where|why|how)\b", lower)),
        }
