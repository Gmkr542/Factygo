from __future__ import annotations

import re
from urllib.parse import urlparse

from app.services.claim_intelligence import ClaimIntelligence


class EvidenceService:
    """Turn question-scoped source passages into evidence for the original claim."""

    def extract(self, documents: list[dict], claim: str) -> list[dict]:
        meta = ClaimIntelligence.analyze(claim)
        evidence: list[dict] = []
        for doc in documents:
            text = doc.get("text", "")
            question = doc.get("research_question", "")
            # A passage is relevant because it answers a framed research question,
            # not only because it repeats words from the original claim.
            terms = self._terms(question or claim)
            sentences = re.split(r"(?<=[.!?])\s+", text)
            candidates = []
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) < 45:
                    continue
                relevance = self._relevance(sentence, terms)
                analysis = self._analyze_sentence(sentence, claim, question, meta, doc)
                # Authoritative question-answer passages can be relevant even
                # when they do not repeat the original claim's subject.
                if relevance < .18 and not analysis["direct_fact_match"]:
                    continue
                score = relevance * .45 + analysis["strength"] * .55
                candidates.append((score, sentence, analysis))
            for score, sentence, analysis in sorted(candidates, reverse=True)[:3]:
                evidence.append({
                    "source_title": doc.get("title", "Untitled"),
                    "source_url": doc.get("url", ""),
                    "excerpt": sentence[:1400],
                    "stance": analysis["stance"],
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
    def _terms(text: str) -> list[str]:
        stop = {"the", "and", "for", "with", "that", "this", "from", "into", "about", "is", "are", "in", "of", "to", "a", "an", "on", "2026", "according"}
        return [x.lower() for x in re.findall(r"[a-zA-Z0-9]+", text) if len(x) >= 3 and x.lower() not in stop]

    @staticmethod
    def _relevance(sentence: str, terms: list[str]) -> float:
        lower = sentence.lower()
        hits = sum(1 for term in terms if term in lower)
        return min(1.0, hits / max(2, len(terms)) + (0.15 if hits >= 2 else 0))

    @classmethod
    def _analyze_sentence(cls, sentence: str, claim: str, question: str, meta: dict, doc: dict) -> dict:
        lower = sentence.lower()
        qlower = question.lower()
        relevance = cls._relevance(sentence, cls._terms(question or claim))
        jurisdiction_match = cls._scope_match(lower, meta)
        domain = urlparse(doc.get("url", "")).netloc.lower().removeprefix("www.")
        if meta["jurisdiction"] == "UNION" and doc.get("source_type") in {"official_government", "official_parliament", "official_electoral"}:
            if domain in {"pmindia.gov.in", "sansad.in", "loksabha.nic.in", "eci.gov.in", "results.eci.gov.in"}:
                jurisdiction_match = True
        temporal_match = cls._time_match(lower, meta.get("year"))
        stance = "contextual"
        reason = "Relevant passage, but it does not directly establish the original claim."
        direct_fact_match = False

        if meta["jurisdiction"] == "UNION" and cls._state_only(lower):
            return {"stance": "contextual", "relevance": relevance * .55, "strength": .15,
                    "jurisdiction_match": False, "temporal_match": temporal_match,
                    "reason": "State-level evidence cannot establish a Union-government claim.",
                    "direct_fact_match": False}

        if meta["claim_type"] == "political_power" and meta["subject"] == "Indian National Congress":
            # Q1: current PM. This is strong evidence about who heads the Union
            # executive even if the sentence never says "Congress".
            asks_pm = "prime minister" in qlower or domain == "pmindia.gov.in"
            asks_government = any(x in qlower for x in ("forms the union government", "lead or form the union government", "party or coalition"))
            asks_election = "lok sabha" in qlower or "election" in qlower

            pm_name = bool(re.search(r"\bnarendra\s+modi\b", lower))
            congress_pm = bool(re.search(r"\b(rahul\s+gandhi|mallikarjun\s+kharge)\b", lower))
            nda = any(x in lower for x in ("bjp-led nda", "bjp led nda", "national democratic alliance", "nda government", "nda-led"))
            congress_government = any(x in lower for x in ("congress-led government", "congress led government", "congress government", "indian national congress-led government"))
            direct_negative = any(p in lower for p in (
                "not the central government", "not the union government", "did not form the government",
                "did not form the union government", "did not win the 2024 lok sabha", "lost the 2024 lok sabha",
                "not in power at the centre", "not in power at the center", "opposition at the centre",
                "opposition at the center", "principal opposition",
            ))
            direct_positive = any(p in lower for p in (
                "formed the government at the centre", "formed the government at the center", "formed the union government",
                "congress-led union government", "congress government at the centre", "congress government at the center",
            ))

            if jurisdiction_match and asks_pm and pm_name and not congress_pm:
                stance = "contradicting"
                direct_fact_match = True
                reason = "The authoritative PMO evidence identifies Narendra Modi as Prime Minister; this contradicts a claim that Congress leads the Union Government."
            elif jurisdiction_match and asks_pm and congress_pm:
                stance = "supporting"
                direct_fact_match = True
                reason = "The authoritative evidence identifies a Congress leader as Prime Minister, supporting the claim's subject."
            elif jurisdiction_match and asks_government and nda and not congress_government:
                stance = "contradicting"
                direct_fact_match = True
                reason = "The authoritative evidence identifies the BJP-led NDA as the governing coalition, contradicting a claim that Congress forms the Union Government."
            elif jurisdiction_match and asks_government and congress_government:
                stance = "supporting"
                direct_fact_match = True
                reason = "The authoritative evidence identifies a Congress-led government, supporting the claim."
            elif jurisdiction_match and asks_election and nda and not congress_government:
                stance = "contradicting"
                direct_fact_match = True
                reason = "The election evidence identifies the NDA as the governing coalition, which weighs against the Congress-government claim."
            elif jurisdiction_match and direct_negative:
                stance = "contradicting"
                direct_fact_match = True
                reason = "Direct Union-government evidence contradicts the claim."
            elif jurisdiction_match and direct_positive and "congress" in lower:
                stance = "supporting"
                direct_fact_match = True
                reason = "Direct Union-government evidence supports the claim's subject."

        if stance == "contextual":
            if any(p in lower for p in ("not ", "did not", "never", "false", "denied", "rejected", "opposition")) and jurisdiction_match:
                stance = "contradicting"
                reason = "The passage contains a direct contradiction cue and matches the claim scope."
            elif meta["claim_type"] != "political_power" and any(p in lower for p in ("ruling", "governing", "government", "in power")) and jurisdiction_match:
                stance = "supporting"
                reason = "The passage directly describes the factual status within the claim scope."

        strength = min(1.0, relevance * (.95 if jurisdiction_match else .5) * (.95 if temporal_match else .8) * (1 + doc.get("source_score", 0) * .2))
        if direct_fact_match:
            strength = max(strength, .78 + min(.2, float(doc.get("source_score", 0)) * .2))
        return {"stance": stance, "relevance": max(relevance, .65 if direct_fact_match else relevance),
                "strength": strength, "jurisdiction_match": jurisdiction_match,
                "temporal_match": temporal_match, "reason": reason,
                "direct_fact_match": direct_fact_match}

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
        if not year:
            return True
        years = [int(x) for x in re.findall(r"\b20\d{2}\b", sentence)]
        return not years or year in years or year - 1 in years or year + 1 in years

    @staticmethod
    def _tier(score: float) -> int:
        if score >= .95:
            return 1
        if score >= .85:
            return 2
        if score >= .75:
            return 3
        return 4
