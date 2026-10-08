class VerdictService:
    """Evidence-based verdict engine.

    It deliberately refuses to guess when evidence is unavailable.
    """

    def evaluate(self, claim: str, evidence: list[dict]) -> dict:
        if not evidence:
            return {
                "verdict": "UNVERIFIED",
                "confidence": 0,
                "explanation": (
                    "Factygo does not have retrieved evidence yet. "
                    "No verdict is generated without evidence."
                ),
            }

        return {
            "verdict": "UNVERIFIED",
            "confidence": 0,
            "explanation": "Evidence evaluation is not configured yet.",
        }
