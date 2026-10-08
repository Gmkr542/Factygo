import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute=30):
        super().__init__(app)
        self.limit = requests_per_minute
        self.requests = defaultdict(list)

    async def dispatch(self, request, call_next):
        # Simple in-memory limiter for MVP/single instance.
        # Replace with Redis for multi-instance production.
        client = request.client.host if request.client else "unknown"
        now = time.time()
        window = now - 60
        recent = [t for t in self.requests[client] if t > window]

        if len(recent) >= self.limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
            )

        recent.append(now)
        self.requests[client] = recent
        return await call_next(request)
