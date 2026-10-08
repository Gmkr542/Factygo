from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimiterMiddleware
from app.api.routes.health import router as health_router
from app.api.routes.investigate import router as investigate_router
from app.api.routes.uploads import router as uploads_router

configure_logging()

app = FastAPI(
    title="Factygo API",
    description="Evidence-first AI investigation platform",
    version="1.0.0",
)

origins = [x.strip() for x in settings.cors_origins.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    RateLimiterMiddleware,
    requests_per_minute=settings.rate_limit_per_minute,
)

app.include_router(health_router, prefix="/api")
app.include_router(investigate_router, prefix="/api")
app.include_router(uploads_router, prefix="/api")


@app.get("/")
def root():
    return {
        "name": "Factygo",
        "status": "running",
        "version": "1.0.0",
        "docs": "/docs",
    }
