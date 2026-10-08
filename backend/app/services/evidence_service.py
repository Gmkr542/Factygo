class EvidenceService:
    """Evidence extraction and stance classification layer."""

    def extract(self, documents: list[dict], claim: str) -> list[dict]:
        # Never fabricate evidence.
        return []
