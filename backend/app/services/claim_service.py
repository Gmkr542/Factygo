import re
from app.schemas.investigation import Claim


def decompose_claim(text: str) -> list[Claim]:
    normalized = text.replace(";", ".")
    # Split on sentence boundaries without breaking common abbreviations (U.S., Dr., Mr.)
    parts = [p.strip() for p in re.split(r"(?<![A-Z][a-z])(?<![A-Z])[.!?]+\s+", normalized) if p.strip()]
    if not parts:
        parts = [text.strip()]
    return [Claim(id=i, text=part, type="statement") for i, part in enumerate(parts[:5], start=1)]
