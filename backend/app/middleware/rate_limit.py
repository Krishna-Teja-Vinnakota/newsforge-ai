import asyncio
import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.security import decode_access_token
from app.core.settings import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Small in-process fixed-window limiter for public ingestion and AI cost control."""

    def __init__(self, app):
        super().__init__(app)
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    @staticmethod
    def _limit_for(request: Request) -> tuple[str, int] | None:
        path = request.url.path
        if path == "/api/v1/telemetry/event":
            return ("telemetry", 60)
        # Reader views and feedback feed ranking, so bound how fast one address can move them.
        if request.method == "POST" and path.startswith("/api/v1/articles/") and path.endswith(("/view", "/feedback")):
            return ("reader", 30)
        # Image generation is far more expensive than text, so it gets its own, smaller budget.
        if request.method == "POST" and path == "/api/v1/agents/image":
            return ("image", settings.image_rate_limit_per_minute)
        # Only calls that can spend model quota count; browsing leads, runs and trend status is free.
        if request.method == "POST" and path.startswith("/api/v1/agents/"):
            return ("agents", 10)
        return None

    @staticmethod
    def _identity(request: Request, scope: str) -> str:
        if scope in {"agents", "image"}:
            authorization = request.headers.get("authorization", "")
            if authorization.lower().startswith("bearer "):
                try:
                    return f"user:{decode_access_token(authorization[7:]).get('sub', 'anonymous')}"
                except Exception:
                    pass
        return f"ip:{request.client.host if request.client else 'unknown'}"

    async def dispatch(self, request: Request, call_next):
        rule = self._limit_for(request)
        if rule is not None:
            scope, limit = rule
            key = f"{scope}:{self._identity(request, scope)}"
            now = time.monotonic()
            async with self._lock:
                window = self._requests[key]
                while window and window[0] <= now - 60:
                    window.popleft()
                if len(window) >= limit:
                    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Try again in a minute."})
                window.append(now)
        return await call_next(request)
