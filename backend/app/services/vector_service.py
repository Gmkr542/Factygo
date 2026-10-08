class VectorService:
    """RAG/vector-search extension point.

    Can later use FAISS or pgvector without changing the investigation API.
    """

    def index(self, documents: list[dict]) -> None:
        return None

    def search(self, query: str, limit: int = 5) -> list[dict]:
        return []
