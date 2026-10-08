from app.schemas.investigation import Claim


def decompose_claim(text: str) -> list[Claim]:
    # Safe deterministic baseline. Replace/augment with an LLM classifier later.
    normalized = text.replace(";", ".")
    parts = [p.strip() for p in normalized.split(".") if p.strip()]
    if not parts:
        parts = [text.strip()]

    return [
        Claim(
            id=i,
            text=part,
            type="statement",
        )
        for i, part in enumerate(parts, start=1)
    ]
