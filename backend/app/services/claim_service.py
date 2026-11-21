import re
from app.schemas.investigation import Claim


def decompose_claim(text: str) -> list[Claim]:
    normalized = text.replace(";", ".")
    # Split on sentence boundaries and strong causal/contrast conjunctions
    raw_parts = re.split(r"(?<![A-Z][a-z])(?<![A-Z])[.!?]+\s+|\b(?:which is why|therefore|however|whereas)\b", normalized, flags=re.I)
    parts = [p.strip(" ,.-") for p in raw_parts if len(p.strip(" ,.-")) >= 8]
    if not parts:
        parts = [text.strip()]
    return [Claim(id=i, text=part, type="statement") for i, part in enumerate(parts[:4], start=1)]
