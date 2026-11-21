from __future__ import annotations

from urllib.parse import urlparse


class VerdictService:
    def evaluate(self, claim: str, evidence: list[dict]) -> dict:
        if not evidence:
            return {
                "verdict": "UNVERIFIED",
                "confidence": 0,
                "explanation": "No sufficiently relevant evidence was retrieved from live web sources.",
                "analysis": {
                    "supporting_count": 0,
                    "contradicting_count": 0,
                    "independent_domains": 0,
                    "limitations": "Search providers returned no matching passages.",
                },
            }

        supporting = [e for e in evidence if e.get("stance") == "supporting"]
        contradicting = [e for e in evidence if e.get("stance") == "contradicting"]
        domains = {
            (e.get("domain") or urlparse(e.get("source_url", "")).netloc).lower().removeprefix("www.")
            for e in evidence
            if e.get("domain") or e.get("source_url")
        }
        domains.discard("")

        sup_weight = sum(e.get("strength", 0.5) for e in supporting)
        con_weight = sum(e.get("strength", 0.5) for e in contradicting)

        if sup_weight > 0 and con_weight == 0:
            verdict = "MOSTLY TRUE" if len(supporting) >= 2 else "PARTLY TRUE"
            confidence = min(85, int(45 + sup_weight * 15))
            explanation = f"Retrieved evidence from {len(domains)} independent domain(s) supports the claim without direct contradiction."
        elif con_weight > 0 and sup_weight == 0:
            verdict = "MOSTLY FALSE" if len(contradicting) >= 2 else "MISLEADING"
            confidence = min(85, int(45 + con_weight * 15))
            explanation = f"Retrieved evidence from {len(domains)} independent domain(s) contradicts the claim."
        elif sup_weight > 0 and con_weight > 0:
            verdict = "PARTLY TRUE"
            confidence = min(75, int(40 + abs(sup_weight - con_weight) * 10))
            explanation = "Retrieved sources show mixed findings with both supporting evidence and caveats."
        else:
            verdict = "UNVERIFIED"
            confidence = min(45, 15 + len(evidence) * 5)
            explanation = "Related sources were retrieved, but none directly confirmed or refuted the specific claim."

        return {
            "verdict": verdict,
            "confidence": confidence,
            "explanation": explanation,
            "analysis": {
                "supporting_count": len(supporting),
                "contradicting_count": len(contradicting),
                "independent_domains": len(domains),
                "limitations": "Evaluated using deterministic evidence scoring.",
            },
        }
