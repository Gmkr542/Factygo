class VerdictService:
    """Conservative verdict layer.

    Research/evidence v1 is intentionally not allowed to turn keyword overlap
    into a factual verdict. A later semantic/LLM evaluator can consume the
    evidence and produce a supported label with calibrated confidence.
    """

    def evaluate(self, claim: str, evidence: list[dict]) -> dict:
        if not evidence:
            return {
                "verdict": "UNVERIFIED",
                "confidence": 0,
                "explanation": "No retrieved evidence is available. Factygo refuses to invent a verdict or source.",
            }

        return {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "confidence": 20,
            "explanation": (
                f"Factygo retrieved {len(evidence)} claim-relevant excerpts, but the current "
                "verdict engine does not convert keyword evidence into a factual conclusion. "
                "A semantic evidence evaluator is required before issuing TRUE/FALSE labels."
            ),
        }
