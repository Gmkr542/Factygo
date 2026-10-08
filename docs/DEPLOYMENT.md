# Render Deployment

## factygo-web
Type: Static Site
Root: `frontend`
Build: `npm install && npm run build`
Publish: `out`
Environment:
`NEXT_PUBLIC_API_URL=https://factygo-api.onrender.com`

## factygo-api
Type: Web Service
Root: `backend`
Build: `pip install -r requirements.txt`
Start:
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Environment:
- DATABASE_URL
- CORS_ORIGINS
- LLM_PROVIDER
- LLM_BASE_URL
- LLM_MODEL
- SEARCH_PROVIDER
- SEARCH_API_KEY
- RATE_LIMIT_PER_MINUTE

### Python runtime
Because the API service uses `Root Directory: backend`, Python runtime files are also present inside `backend/`:
- `backend/.python-version` → `3.12.10`
- `backend/runtime.txt` → `python-3.12.10`

The repository root also contains the same pins for local/repo tooling.

After pushing, Render should show:
`Using Python version 3.12.10`

If it still selects 3.14, check the Render service's Environment/Runtime settings for a manually configured Python version and set it to 3.12.10.

## PostgreSQL
Create a Render PostgreSQL database and put its internal connection URL into `DATABASE_URL`.

Do not commit secrets.
