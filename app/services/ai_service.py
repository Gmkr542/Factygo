import asyncio
from app.services.groq_service import _request_bounded
from app.core.config import get_settings


class AIService:
    """Provider-neutral LLM interface backed by Groq."""

    def complete(self, prompt: str) -> str:
        s = get_settings()
        return asyncio.run(_request_bounded(s.groq_model, prompt))
