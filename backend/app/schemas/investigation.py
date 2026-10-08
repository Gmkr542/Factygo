from pydantic import BaseModel, Field
from typing import List


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
    source_tier: int = 4


class Evidence(BaseModel):
    source_title: str
    source_url: str
    excerpt: str
    stance: str
    relevance: float = 0
    source_score: float = 0
    source_tier: int = 4
    jurisdiction_match: bool = True
    temporal_match: bool = True
    strength: float = 0
    reason: str = ""


class ResearchQuestion(BaseModel):
    id: int
    question: str
    raw_answer: str = ""
    sources: List[Source] = []
    evidence_count: int = 0
    status: str = "no_results"


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
    claim_analysis: dict = {}
    evidence_analysis: dict = {}
    research_questions: List[ResearchQuestion] = []
