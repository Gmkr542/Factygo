# Factygo

## Evidence-first AI investigation platform

Factygo turns claims, social posts and documents into structured investigations.

### Core pipeline
Input → Claim extraction → Claim decomposition → Research → Source ranking → Evidence extraction → Contradiction analysis → Verdict → Confidence → Report

### Target capabilities
- Text/social claim investigation
- Compound claim decomposition
- Web research provider abstraction
- Source normalization and scoring
- Supporting/contradicting/context evidence
- Evidence-first verdicts
- Confidence + uncertainty
- Citation mapping
- OCR/document ingestion hooks
- PostgreSQL persistence
- RAG/vector-search extension point
- AI provider abstraction
- Authentication-ready architecture
- Rate limiting hooks
- Structured logging
- Background-job architecture
- Tests
- Docker
- GitHub Actions
- Render deployment

### Current MVP behavior
The repository is safe by default: if research evidence is unavailable, Factygo returns `UNVERIFIED`. It never invents sources.

### Free-cost development
The architecture is provider-independent. You can use local Ollama/open-source models and local PostgreSQL/vector search during development, avoiding paid AI APIs.

## Backend

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs: http://127.0.0.1:8000/docs

## Frontend

```bash
cd frontend
npm install
npm run dev
```

## Environment

Copy `.env.example` to `.env`.

Never commit real secrets.

## Render
See `docs/DEPLOYMENT.md`.
