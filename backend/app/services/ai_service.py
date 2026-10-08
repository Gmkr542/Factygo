class AIService:
    """Provider-neutral LLM interface.

    Local Ollama or another provider can be implemented here.
    """

    def complete(self, prompt: str) -> str:
        raise NotImplementedError("Configure an AI provider.")
