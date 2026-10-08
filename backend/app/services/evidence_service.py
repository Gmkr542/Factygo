from __future__ import annotations

import re
from urllib.parse import urlparse

from app.services.claim_intelligence import ClaimIntelligence


class EvidenceService:
    """Claim-aware evidence extraction with scope, time and stance checks."""

    def extract(self, documents: list[dict], claim: str) -> list[dict]:
        meta = ClaimIntelligence.analyze(claim)
        terms = self._terms(claim)
        evidence = []
        for doc in documents:
            text = doc.get("text", "")
            sentences = re.split(r"(?<=[.!?])\s+", text)
            candidates = []
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) < 45: continue
                relevance = self._relevance(sentence, terms)
                if relevance < .18: continue
                analysis = self._analyze_sentence(sentence, claim, meta, doc)
                score = relevance * .55 + analysis["strength"] * .45
                candidates.append((score, sentence, analysis))
            for score, sentence, analysis in sorted(candidates, reverse=True)[:3]:
                evidence.append({
                    "source_title": doc.get("title", "Untitled"), "source_url": doc.get("url", ""),
                    "excerpt": sentence[:1400], "stance": analysis["stance"],
                    "relevance": round(min(1, analysis["relevance"]), 3),
                    "source_score": float(doc.get("source_score", 0)),
                    "source_tier": self._tier(doc.get("source_score", 0)),
                    "jurisdiction_match": analysis["jurisdiction_match"],
                    "temporal_match": analysis["temporal_match"],
                    "strength": round(analysis["strength"], 3),
                    "reason": analysis["reason"],
                })
        evidence.sort(key=lambda x: (x["strength"], x["relevance"], x["source_score"]), reverse=True)
        return evidence[:15]

    @staticmethod
    def _terms(claim: str) -> list[str]:
        stop = {"the", "and", "for", "with", "that", "this", "from", "into", "about", "is", "are", "in", "of", "to", "a", "an", "on", "2026"}
        return [x.lower() for x in re.findall(r"[a-zA-Z0-9]+", claim) if len(x) >= 3 and x.lower() not in stop]

    @staticmethod
    def _relevance(sentence: str, terms: list[str]) -> float:
        lower = sentence.lower()
        hits = sum(1 for term in terms if term in lower)
        return min(1.0, hits / max(2, len(terms)) + (0.15 if hits >= 2 else 0))

    @classmethod
    def _analyze_sentence(cls, sentence: str, claim: str, meta: dict, doc: dict) -> dict:
        lower = sentence.lower()
        relevance = cls._relevance(sentence, cls._terms(claim))
        jurisdiction_match = cls._scope_match(lower, meta)
        if meta["jurisdiction"] == "UNION" and doc.get("source_type") in {"official_government", "official_parliament"}:
            domain = urlparse(doc.get("url", "")).netloc.lower().removeprefix("www.")
            if domain in {"pmindia.gov.in", "sansad.in", "loksabha.nic.in"}:
                jurisdiction_match = True
        temporal_match = cls._time_match(lower, meta.get("year"))
        stance = "contextual"
        reason = "Relevant passage, but it does not directly establish the claim."
        if meta["jurisdiction"] == "UNION" and cls._state_only(lower):
            return {"stance": "contextual", "relevance": relevance * .55, "strength": .15, "jurisdiction_match": False, "temporal_match": temporal_match, "reason": "State-level evidence cannot establish a Union-government claim."}

        if meta["claim_type"] == "political_power" and meta["subject"] == "Indian National Congress":
            direct_negative = any(p in lower for p in (
                "not the central government", "not the union government", "did not form the government", "did not form the union government",
                "did not win the 2024 lok sabha", "lost the 2024 lok sabha", "not in power at the centre", "not in power at the center",
                "opposition at the centre", "opposition at the center", "principal opposition",
            ))
            direct_positive = any(p in lower for p in (
                "formed the government at the centre", "formed the government at the center", "formed the union government",
                "congress-led union government", "congress government at the centre", "congress government at the center",
            ))
            authority_negative = any(p in lower for p in (
                "prime minister narendra modi",
                "prime minister of india: narendra modi",
                "narendra modi is the prime minister",
                "narendra modi, prime minister",
            ))
            authority_positive = any(p in lower for p in (
                "prime minister rahul gandhi",
                "congress-led government",
                "indian national congress-led government",
            ))
            subject_absent_lead = any(p in lower for p in (
                "bjp-led", "nda-led", "bjp led", "national democratic alliance",
            )) and "congress" not in lower
            if subject_absent_lead and jurisdiction_match:
                stance, reason = "contradicting", "The authoritative passage identifies another party or coalition as leading the Union Government."
            elif direct_negative and jurisdiction_match:
                stance, reason = "contradicting", "Direct Union-government evidence contradicts the claim."
            elif direct_positive and jurisdiction_match and "congress" in lower:
                stance, reason = "supporting", "Direct Union-government evidence supports the claim's subject."
            elif authority_negative and jurisdiction_match:
                stance, reason = "contradicting", "An authoritative government record identifies a different current Union executive than the claim's subject."
            elif authority_positive and jurisdiction_match:
                stance, reason = "supporting", "An authoritative record directly identifies the claim's subject as leading the Union government."
        if stance == "contextual":
            if any(p in lower for p in ("not ", "did not", "never", "false", "denied", "rejected", "opposition")) and jurisdiction_match:
                stance = "contradicting"; reason = "The passage contains a direct contradiction cue and matches the claim scope."
            elif any(p in lower for p in ("ruling", "governing", "government", "in power")) and jurisdiction_match:
                stance = "supporting"; reason = "The passage directly describes governing power within the claim scope."
        strength = min(1.0, relevance * (.95 if jurisdiction_match else .5) * (.95 if temporal_match else .8) * (1 + doc.get("source_score", 0) * .2))
        return {"stance": stance, "relevance": relevance, "strength": strength, "jurisdiction_match": jurisdiction_match, "temporal_match": temporal_match, "reason": reason}

    @staticmethod
    def _scope_match(sentence: str, meta: dict) -> bool:
        if meta["jurisdiction"] == "UNION":
            return any(p in sentence for p in ("central government", "union government", "government of india", "lok sabha", "centre", "center", "national government"))
        if meta["jurisdiction"] == "STATE":
            return True
        return True

    @staticmethod
    def _state_only(sentence: str) -> bool:
        state_markers = ("kerala", "tamil nadu", "karnataka", "rajasthan", "punjab", "assembly election", "state government", "udf", "state polls")
        union_markers = ("lok sabha", "union government", "central government", "government of india", "centre", "center")
        return any(x in sentence for x in state_markers) and not any(x in sentence for x in union_markers)

    @staticmethod
    def _time_match(sentence: str, year: int | None) -> bool:
        if not year: return True
        years = [int(x) for x in re.findall(r"\b20\d{2}\b", sentence)]
        return not years or year in years or year - 1 in years or year + 1 in years

    @staticmethod
    def _tier(score: float) -> int:
        if score >= .95: return 1
        if score >= .85: return 2
        if score >= .75: return 3
        return 4
