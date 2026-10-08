# Factygo Deployment

## Render services

### factygo-web
- Type: Static Site
- Root Directory: `frontend`
- Build: `npm install && npm run build`
- Publish Directory: `out`
- Environment: `NEXT_PUBLIC_API_URL=https://factygo-api.onrender.com`

### factygo-api
- Type: Web Service
- Root Directory: `backend`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Environment:
  - `DATABASE_URL=<Render PostgreSQL URL>`
  - `CORS_ORIGINS=https://factygo-web.onrender.com`

### factygo-db
- Type: PostgreSQL
- Keep it in the same region as the API.

## Python runtime

The repository pins Python 3.12.10 using both:
- `.python-version`
- `runtime.txt`

This avoids Render selecting Python 3.14 for the current dependency set.

## Important

Never commit real API keys or database passwords.
