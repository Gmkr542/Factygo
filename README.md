# Factygo

## Evidence-first AI investigation platform

**Live Web App:** https://onrender.com  
**Live API Docs:** https://onrender.com

Factygo turns claims, questions, and social posts into structured, evidence-grounded investigations.

### Core pipeline
Input → Claim normalization & decomposition → Domain-targeted research → Multi-provider retrieval (DDGS, Google News RSS, PubMed, Wikipedia) → Source authority scoring → Single-pass AI synthesis & TTL caching → Verdict & breakdown report

### Target & implemented capabilities
- Text and question claim investigation with interactive prompt suggestions
- Atomic claim decomposition and domain routing
- Multi-provider web research abstraction (`DDGS`, Google News RSS, NCBI PubMed E-utilities, MediaWiki/Wikipedia) with a 60-second circuit breaker
- Canonical URL deduplication, publisher diversity filtering, and source authority scoring
- Supporting, contradicting, and contextual evidence extraction (`E01–E05`)
- Evidence-first verdicts (`TRUE`, `MOSTLY TRUE`, `PARTLY TRUE`, `MISLEADING`, `MOSTLY FALSE`, `FALSE`, `UNVERIFIED`)
- Calibrated confidence scoring and independent domain corroboration
- Single-pass closed-book Groq AI synthesis (`~85%` token reduction) with 1-hour in-memory TTL response caching
- Deterministic scoring fallback (`VerdictService`) for zero-downtime resilience
- Structured two-part reporting (`Result` summary + `Verdict Breakdown`)
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
- Render monorepo deployment (`backend/` + `frontend/`)

### Current behavior
The repository is safe by default: if reliable research evidence is unavailable, Factygo returns `UNVERIFIED` and never invents sources or citations. When `GROQ_API_KEY` is configured, it runs single-pass closed-book synthesis over the top 5 authoritative sources; otherwise, it automatically falls back to deterministic evidence evaluation.

### Free-cost development
The architecture works out of the box with zero paid API keys using deterministic evaluation, or with a free-tier `GROQ_API_KEY` and local development setup.

## Backend

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs: http://127.0.0

## Frontend

```bash
cd frontend
npm install
npm run dev
```

## Environment

Copy `.env.example` to `.env` (and set `GROQ_API_KEY` on `factygo-api` and `NEXT_PUBLIC_API_URL` on `factygo-web` in Render).

Never commit real secrets.

## Render
See `docs/DEPLOYMENT.md`.
