# Factygo

**Evidence-first AI investigation platform**

Factygo investigates claims instead of simply generating an answer.

## Planned workflow

Claim/Post/URL/Image/PDF
→ Claim extraction
→ Claim decomposition
→ Web research
→ Source ranking
→ Evidence extraction
→ Supporting/contradicting evidence
→ Contradiction analysis
→ Verdict
→ Confidence
→ Citation-backed investigation report

## Current repository

This starter contains:
- FastAPI backend
- Next.js frontend
- Structured investigation API
- Claim decomposition module
- Research/evidence/verdict service interfaces
- OCR/document extension points
- PostgreSQL-ready configuration
- Render configuration
- GitHub Actions tests
- Docker configuration
- API documentation through FastAPI `/docs`

The current implementation intentionally returns `UNVERIFIED` until real research/LLM providers are connected. This prevents fabricated evidence.

## Run backend

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend: http://127.0.0.1:8000
Docs: http://127.0.0.1:8000/docs

## Run frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:3000

Set `NEXT_PUBLIC_API_URL` if the backend is not on localhost.

## Render

The backend can be deployed using `render.yaml`.

Recommended production environment variables:
- `DATABASE_URL`
- `LLM_API_KEY` (when an LLM provider is added)
- `SEARCH_API_KEY` (when a search provider is added)
- `CORS_ORIGINS`

Never commit API keys.

## Roadmap

V1 Web research
V2 Source extraction/ranking
V3 AI evidence comparison
V4 Claim decomposition
V5 Investigation reports
V6 OCR + screenshots
V7 PDF/DOCX investigation
V8 PostgreSQL history
V9 RAG/semantic retrieval
V10 Research agent
V11 Evaluation/quality metrics
V12 Production security, caching, async workers and monitoring
