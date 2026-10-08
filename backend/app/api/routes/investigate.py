from fastapi import APIRouter
from app.schemas.investigation import InvestigationRequest, InvestigationResponse
from app.services.investigation_service import investigate

router = APIRouter(prefix="/investigate", tags=["investigation"])


@router.post("", response_model=InvestigationResponse)
def create_investigation(request: InvestigationRequest):
    return investigate(request.text)
