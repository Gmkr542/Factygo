from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional


class InvestigationRequest(BaseModel):
    text: str = Field(min_length=3, max_length=10000)


class Claim(BaseModel):
    id: int
    text: str
    type: str = "unknown"


class Source(BaseModel):
    title: str
    url: str
    domain: str = ""
    source_score: float = 0
    source_type: str = "unknown"


class Evidence(BaseModel):
    source_title: str
    source_url: str
    excerpt: str
    stance: str
    relevance: float = 0
    source_score: float = 0


class InvestigationResponse(BaseModel):
    claim: str
    claims: List[Claim]
    verdict: str
    confidence: int
    explanation: str
    evidence: List[Evidence]
    sources: List[Source] = []
    status: str
    methodology: List[str] = []
