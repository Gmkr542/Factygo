import time
from collections import defaultdict, deque
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 30):
        super().__init__(app)
        self.limit = requests_per_minute
        self.window = 60.0
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            ip = request.client.host if request.client else "unknown"
            now = time.monotonic()
            q = self.hits[ip]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return JSONResponse(
                    {"detail": "Rate limit exceeded. Please retry shortly."},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
            q.append(now)
        return await call_next(request)
