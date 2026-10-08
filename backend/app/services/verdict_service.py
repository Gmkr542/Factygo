from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlparse


class VerdictService:
    """Transparent evidence-weighted verdict engine.

    This is a deterministic v2 baseline. It does not pretend that lexical
    matching is full semantic entailment. A future local/hosted model can plug
    into the same evidence fields and replace only the semantic scoring step.
    """

    LABELS = {
        "TRUE", "MOSTLY_TRUE", "PARTLY_TRUE", "MISLEADING",
        "MOSTLY_FALSE", "FALSE", "UNVERIFIED", "INSUFFICIENT_EVIDENCE",
    }

    def evaluate(self, claim: str, evidence: list[dict]) -> dict:
        usable = [e for e in evidence if e.get("relevance", 0) >= 0.35]
        if not usable:
            return self._empty("No sufficiently relevant evidence was retrieved.")

        support = [e for e in usable if e.get("stance") == "supporting"]
        contradict = [e for e in usable if e.get("stance") == "contradicting"]
        contextual = [e for e in usable if e.get("stance") == "contextual"]

        support_score = self._aggregate(support)
        contradict_score = self._aggregate(contradict)
        support_domains = self._independent_domains(support)
        contradict_domains = self._independent_domains(contradict)

        if not support and not contradict:
            return {
                "verdict": "INSUFFICIENT_EVIDENCE",
                "confidence": self._confidence(0.0, 0, 0, len(contextual)),
                "explanation": self._explain_unknown(len(usable), len(contextual)),
                "analysis": self._analysis(support, contradict, contextual),
            }

        # Independent corroboration is capped to avoid letting many excerpts
        # from one website masquerade as many independent sources.
        support_score += min(0.20, max(0, len(support_domains) - 1) * 0.07)
        contradict_score += min(0.20, max(0, len(contradict_domains) - 1) * 0.07)

        total = support_score + contradict_score
        if total <= 0.35:
            return {
                "verdict": "INSUFFICIENT_EVIDENCE",
                "confidence": 25,
                "explanation": "Relevant passages were found, but their relationship to the claim is not strong enough for a reliable verdict.",
                "analysis": self._analysis(support, contradict, contextual),
            }

        if support_score > 0 and contradict_score > 0:
            ratio = abs(support_score - contradict_score) / total
            if ratio < 0.25:
                label = "PARTLY_TRUE" if support_score >= contradict_score else "MISLEADING"
            elif support_score > contradict_score:
                label = "MOSTLY_TRUE" if contradict_score > 0 else "TRUE"
            else:
                label = "MOSTLY_FALSE" if support_score > 0 else "FALSE"
        elif support_score > contradict_score:
            label = "TRUE" if support_score >= 1.15 else "MOSTLY_TRUE"
        else:
            label = "FALSE" if contradict_score >= 1.15 else "MOSTLY_FALSE"

        winning = max(support_score, contradict_score)
        opposing = min(support_score, contradict_score)
        confidence = self._confidence(winning, len(support_domains) if support_score >= contradict_score else len(contradict_domains), len(usable), len(contextual), opposing)

        return {
            "verdict": label,
            "confidence": confidence,
            "explanation": self._explain(label, support, contradict, support_domains, contradict_domains),
            "analysis": self._analysis(support, contradict, contextual),
        }

    @staticmethod
    def _aggregate(items: list[dict]) -> float:
        return sum(
            float(e.get("relevance", 0))
            * float(e.get("strength", 0.5))
            * (0.65 + 0.35 * float(e.get("source_score", 0.5)))
            for e in items
        )

    @staticmethod
    def _independent_domains(items: list[dict]) -> set[str]:
        domains = set()
        for e in items:
            domain = e.get("domain") or urlparse(e.get("source_url", "")).netloc
            if domain:
                domains.add(domain.lower().removeprefix("www."))
        return domains

    @staticmethod
    def _confidence(winning: float, independent: int, usable: int, contextual: int, opposing: float = 0) -> int:
        base = 35 + min(35, winning * 18) + min(20, max(0, independent - 1) * 8)
        if opposing:
            base -= min(25, opposing * 12)
        if contextual >= usable / 2:
            base -= 10
        return max(10, min(99, round(base)))

    @staticmethod
    def _empty(message: str) -> dict:
        return {"verdict": "UNVERIFIED", "confidence": 0, "explanation": message, "analysis": {}}

    @staticmethod
    def _explain(label, support, contradict, support_domains, contradict_domains):
        if label in {"TRUE", "MOSTLY_TRUE"}:
            return f"The retrieved evidence leans toward the claim, with {len(support_domains)} independent source domain(s) providing supporting evidence."
        if label in {"FALSE", "MOSTLY_FALSE"}:
            return f"The retrieved evidence contradicts the claim, with {len(contradict_domains)} independent source domain(s) providing contradictory evidence."
        if label in {"PARTLY_TRUE", "MISLEADING"}:
            return "The evidence is mixed: meaningful supporting and contradicting material was retrieved, so a binary true/false conclusion would overstate the evidence."
        return "The retrieved material is relevant but not strong or independent enough to establish the claim."

    @staticmethod
    def _explain_unknown(total, contextual):
        return f"Factygo retrieved {total} relevant passages, but {contextual} were contextual rather than sufficiently explicit support or contradiction."

    @staticmethod
    def _analysis(support, contradict, contextual):
        return {
            "supporting_count": len(support),
            "contradicting_count": len(contradict),
            "contextual_count": len(contextual),
            "supporting_domains": sorted(VerdictService._independent_domains(support)),
            "contradicting_domains": sorted(VerdictService._independent_domains(contradict)),
        }
