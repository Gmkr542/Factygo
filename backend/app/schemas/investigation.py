from pydantic import BaseModel, Field
from typing import List


class InvestigationRequest(BaseModel):
    text: str = Field(min_length=3, max_length=10000)


class Claim(BaseModel):
    id: int
    text: str
    type: str = "unknown"


class Evidence(BaseModel):
    title: str
    url: str
    excerpt: str
    stance: str  # supporting / contradicting / contextual


class InvestigationResponse(BaseModel):
    claim: str
    claims: List[Claim]
    verdict: str
    confidence: int
    explanation: str
    evidence: List[Evidence]
    status: str
