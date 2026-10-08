from app.schemas.investigation import Claim


def decompose_claim(text: str) -> list[Claim]:
    # Deterministic MVP decomposition.
    # Later this can use an LLM to split compound claims.
    parts = [p.strip() for p in text.replace(";", ".").split(".") if p.strip()]

    if not parts:
        parts = [text.strip()]

    return [
        Claim(id=index, text=part, type="unknown")
        for index, part in enumerate(parts, start=1)
    ]
