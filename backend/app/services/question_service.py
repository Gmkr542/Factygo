from __future__ import annotations

import re


class QuestionService:
    """Break an investigation into independently researchable questions.

    Questions are research tasks, not verdicts. Their raw research is later
    combined and evaluated against the original investigation input.
    """

    POLITICAL_MARKERS = (
        "congress", "bjp", "aap", "party", "ruling", "government",
        "central government", "union government", "prime minister",
        "president", "election", "in power", "governing", "lok sabha",
    )

    @classmethod
    def frame(cls, claim: str, claim_analysis: dict | None = None) -> list[str]:
        text = re.sub(r"\s+", " ", claim).strip()
        lower = text.lower()
        analysis = claim_analysis or {}
        questions: list[str] = []

        # Political/current-power claims need several independent facts before
        # the original claim can be resolved.
        political = analysis.get("claim_type") == "political_power" or any(
            marker in lower for marker in cls.POLITICAL_MARKERS
        )
        current = bool(re.search(r"\b20\d{2}\b", lower)) or any(
            x in lower for x in ("current", "currently", "today", "now", "latest")
        )

        if political:
            if "prime minister" in lower or "government" in lower or "ruling" in lower or "in power" in lower:
                questions.append("Who is the current Prime Minister of India, according to an authoritative source?")
            questions.append("Which party or coalition currently forms the Union Government of India?")
            questions.append("What do the latest Lok Sabha election results establish about the governing party or coalition?")
            questions.append("Does the party named in the original claim currently lead or form the Union Government?")
            if current:
                questions.append("Have there been any subsequent changes to the Union Government relevant to the claim's stated date?")
        else:
            # Generic factual claims: identify the core subject, status, and
            # strongest primary/independent corroboration needed to resolve it.
            questions.extend([
                f"What authoritative sources establish the factual status of: {text}",
                f"What primary or original source evidence is available for: {text}",
                f"What reliable evidence contradicts or limits this claim: {text}",
            ])

        # Keep questions independent and deterministic.
        result: list[str] = []
        seen: set[str] = set()
        for question in questions:
            q = re.sub(r"\s+", " ", question).strip()
            if q.lower() not in seen:
                result.append(q)
                seen.add(q.lower())
        return result[:5]
