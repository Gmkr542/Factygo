class VerdictService:
    """Transparent verdict engine.

    Supported final labels:
    TRUE, MOSTLY_TRUE, PARTLY_TRUE, MISLEADING,
    MOSTLY_FALSE, FALSE, UNVERIFIED, INSUFFICIENT_EVIDENCE
    """

    def evaluate(self, claim: str, evidence: list[dict]) -> dict:
        if not evidence:
            return {
                "verdict": "UNVERIFIED",
                "confidence": 0,
                "explanation": (
                    "No retrieved evidence is available. Factygo refuses "
                    "to invent a verdict or source."
                ),
            }

        return {
            "verdict": "UNVERIFIED",
            "confidence": 0,
            "explanation": "Evidence evaluation is not configured.",
        }
