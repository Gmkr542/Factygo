from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlparse


class VerdictService:
    """Evidence-weighted verdicting with scope-aware corroboration."""

    LABELS = ("TRUE", "MOSTLY_TRUE", "PARTLY_TRUE", "MISLEADING", "MOSTLY_FALSE", "FALSE", "UNVERIFIED", "INSUFFICIENT_EVIDENCE")

    def evaluate(self, claim: str, evidence: list[dict]) -> dict:
        if not evidence:
            return {"verdict": "UNVERIFIED", "confidence": 0, "explanation": "No sufficiently relevant evidence was retrieved.", "analysis": {"supporting": 0, "contradicting": 0, "contextual": 0, "independent_domains": 0}}
        support = [e for e in evidence if e["stance"] == "supporting" and e.get("jurisdiction_match", True)]
        oppose = [e for e in evidence if e["stance"] == "contradicting" and e.get("jurisdiction_match", True)]
        contextual = [e for e in evidence if e["stance"] == "contextual"]
        support_domains = self._domains(support); oppose_domains = self._domains(oppose)
        s = self._weighted(support); o = self._weighted(oppose)
        total = s + o
        if total < .35:
            verdict, confidence = "INSUFFICIENT_EVIDENCE", min(45, int(total * 60))
        elif o >= 1.7 * max(s, .01):
            verdict = "FALSE"; confidence = self._confidence(o, s, oppose_domains)
        elif s >= 1.7 * max(o, .01):
            verdict = "TRUE"; confidence = self._confidence(s, o, support_domains)
        elif o > s * 1.15:
            verdict = "MOSTLY_FALSE"; confidence = self._confidence(o, s, oppose_domains)
        elif s > o * 1.15:
            verdict = "MOSTLY_TRUE"; confidence = self._confidence(s, o, support_domains)
        else:
            verdict, confidence = "UNVERIFIED", min(60, max(25, int(50 * total)))
        if verdict == "FALSE":
            explanation = "The strongest relevant evidence contradicts the claim, with scope-matched sources outweighing supporting evidence."
        elif verdict == "TRUE":
            explanation = "The strongest relevant evidence supports the claim, with scope-matched sources outweighing contradictions."
        elif verdict == "MOSTLY_FALSE":
            explanation = "Evidence leans against the claim, but the available record is not strong enough for a definitive FALSE label."
        elif verdict == "MOSTLY_TRUE":
            explanation = "Evidence leans toward the claim, but the available record is not strong enough for a definitive TRUE label."
        else:
            explanation = "The retrieved evidence is relevant but does not establish a sufficiently one-sided conclusion."
        return {"verdict": verdict, "confidence": confidence, "explanation": explanation, "analysis": {"supporting": len(support), "contradicting": len(oppose), "contextual": len(contextual), "independent_domains": len(support_domains | oppose_domains), "supporting_domains": sorted(support_domains), "contradicting_domains": sorted(oppose_domains)}}

    @staticmethod
    def _weighted(items: list[dict]) -> float:
        return sum(float(e.get("strength", 0)) * (0.7 + float(e.get("source_score", 0)) * .3) for e in items)

    @staticmethod
    def _domains(items: list[dict]) -> set[str]:
        return {urlparse(e.get("source_url", "")).netloc.lower().removeprefix("www.") for e in items if e.get("source_url")}

    @staticmethod
    def _confidence(winner: float, loser: float, domains: set[str]) -> int:
        ratio = winner / max(winner + loser, .01)
        corroboration = min(.15, max(0, len(domains) - 1) * .05)
        return min(99, max(50, int((ratio + corroboration) * 100)))
