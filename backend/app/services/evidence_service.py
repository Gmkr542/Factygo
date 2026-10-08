class EvidenceService:
    """Turn retrieved documents into claim-relevant evidence."""

    def extract(self, documents: list[dict], claim: str) -> list[dict]:
        # Never fabricate evidence.
        return []
