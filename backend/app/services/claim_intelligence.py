from __future__ import annotations

import re
from datetime import datetime


class ClaimIntelligence:
    """Deterministic claim normalization used before web evidence is judged."""

    UNION_TERMS = {
        "centre", "center", "central government", "union government", "government of india",
        "national government", "central govt", "union govt", "lok sabha government",
    }
    STATE_TERMS = {"state government", "state", "kerala", "tamil nadu", "karnataka", "telangana", "andhra pradesh", "rajasthan", "punjab", "himachal pradesh", "chhattisgarh", "west bengal", "odisha", "assam", "goa", "maharashtra", "gujarat", "madhya pradesh", "uttar pradesh", "bihar", "jharkhand", "uttarakhand", "haryana", "manipur", "meghalaya", "mizoram", "nagaland", "tripura", "sikkim", "arunachal pradesh"}
    PARTY_TERMS = {"congress", "inc", "indian national congress", "bjp", "aap", "dmk", "tdp", "ycp"}

    @classmethod
    def analyze(cls, claim: str) -> dict:
        text = re.sub(r"\s+", " ", claim).strip()
        lower = text.lower()
        year_match = re.search(r"\b(20\d{2})\b", lower)
        year = int(year_match.group(1)) if year_match else None
        if not year and any(x in lower for x in ("current", "today", "now")):
            year = datetime.utcnow().year

        jurisdiction = "UNION" if any(term in lower for term in cls.UNION_TERMS) else "STATE" if any(term in lower for term in cls.STATE_TERMS) else "UNKNOWN"
        subject = "Indian National Congress" if any(t in lower for t in ("congress", "inc", "indian national congress")) else "UNKNOWN"
        claim_type = "political_power" if subject != "UNKNOWN" and any(t in lower for t in ("ruling", "government", "power", "in power", "governing")) else "general"
        return {
            "normalized": text,
            "subject": subject,
            "jurisdiction": jurisdiction,
            "year": year,
            "claim_type": claim_type,
            "scope_terms": sorted(cls.UNION_TERMS & set(re.findall(r"[a-z ]+", lower))) if jurisdiction == "UNION" else [],
        }
