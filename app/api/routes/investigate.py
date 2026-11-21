import logging
from fastapi import APIRouter, HTTPException
from app.schemas.investigation import InvestigateRequest, InvestigationResponse
from app.services.article_parser import ArticleFetchError, fetch_article
from app.services.groq_service import GroqPayloadTooLargeError, GroqProviderError, GroqRateLimitError
from app.services.investigation_service import investigate_async

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/investigate", response_model=InvestigationResponse)
async def run_investigation(req: InvestigateRequest):
    raw_input = req.resolved_text()
    if not raw_input:
        raise HTTPException(status_code=400, detail="Please provide a claim, question, or URL to investigate.")

    # Support direct URL investigation seamlessly if user enters an http(s) link
    if raw_input.startswith(("http://", "https://")) and " " not in raw_input:
        try:
            title, body = await fetch_article(raw_input)
            raw_input = f"{title}. {body[:1500]}".strip()
        except ArticleFetchError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return await investigate_async(raw_input)
    except GroqPayloadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except GroqRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(max(1, int(exc.retry_after)))},
        ) from exc
    except GroqProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Investigation failed")
        raise HTTPException(status_code=502, detail="Unable to complete investigation right now.") from exc
