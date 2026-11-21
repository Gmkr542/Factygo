from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


class InvestigateRequest(BaseModel):
    claim: str | None = None
    text: str | None = None
    query: str | None = None
    url: str | None = None
    mode: str = "auto"

    def resolved_text(self) -> str:
        return (self.claim or self.text or self.query or self.url or "").strip()


class Claim(BaseModel):
    id: int
    text: str
    type: str = "statement"


class ResearchQuestion(BaseModel):
    id: int
    question: str
    raw_answer: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    evidence_count: int = 0
    status: str = "researched"


class InvestigationResponse(BaseModel):
    claim: str
    claims: list[Claim] = Field(default_factory=list)
    claim_verdicts: list[dict[str, Any]] = Field(default_factory=list)
    computed_facts: list[str] = Field(default_factory=list)
    verdict: str = "UNVERIFIED"
    confidence: int = 0
    explanation: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "complete"
    methodology: list[str] = Field(default_factory=list)
    claim_analysis: dict[str, Any] = Field(default_factory=dict)
    evidence_analysis: dict[str, Any] = Field(default_factory=dict)
    research_questions: list[ResearchQuestion] = Field(default_factory=list)
