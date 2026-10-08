from urllib.parse import urlparse
from app.schemas.investigation import Source


class ResearchService:
    """Provider-independent web research layer.

    Implement a free/local/provider adapter here later.
    Keep search-provider details outside the investigation engine.
    """

    def search(self, query: str) -> list[dict]:
        # No provider configured: return no evidence rather than hallucinating.
        return []

    def normalize(self, documents: list[dict]) -> list[Source]:
        results = []
        for doc in documents:
            url = doc.get("url", "")
            domain = urlparse(url).netloc
            results.append(
                Source(
                    title=doc.get("title", "Untitled"),
                    url=url,
                    domain=domain,
                    source_score=float(doc.get("source_score", 0)),
                    source_type=doc.get("source_type", "unknown"),
                )
            )
        return results
