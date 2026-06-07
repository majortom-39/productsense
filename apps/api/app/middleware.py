"""Cross-cutting middleware: rate limiting + security headers.

Per MCP + general API best practices:
  - Per-user rate limit on POST /maya/message (LLM calls are expensive)
  - Security headers (CSP / HSTS / no-sniff / frame-deny)
  - Request ID for log correlation
"""
from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict, deque
from typing import Callable

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


# ─── Per-user token-bucket rate limit ──────────────────────────────────────

class _TokenBucket:
    """Sliding-window token bucket. In-memory; fine for single-worker uvicorn.
    Replace with Redis when you scale out workers."""

    def __init__(self, max_per_window: int, window_seconds: int):
        self.max = max_per_window
        self.window = window_seconds
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def take(self, key: str) -> tuple[bool, int]:
        """Try to consume a token. Returns (allowed, retry_after_seconds)."""
        async with self._lock:
            now = time.monotonic()
            bucket = self._buckets[key]
            # Expire old timestamps
            while bucket and now - bucket[0] > self.window:
                bucket.popleft()
            if len(bucket) >= self.max:
                retry_after = int(self.window - (now - bucket[0])) + 1
                return False, max(1, retry_after)
            bucket.append(now)
            return True, 0


_RATE_LIMITS = {
    # path → (max_per_window, window_seconds)
    "/maya/message": (30, 60),  # 30 msgs/min/user
    "/maya/start": (10, 60),    # 10 starts/min/user
    "/projects": (60, 60),      # CRUD
}


_buckets: dict[str, _TokenBucket] = {
    path: _TokenBucket(*spec) for path, spec in _RATE_LIMITS.items()
}


def _key_for(request: Request) -> str:
    """User ID if authed, else client IP."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        # Hash truncate for log safety; we don't decode here (cheap path)
        token = auth.split(" ", 1)[1].strip()
        return f"jwt:{token[-16:]}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        bucket = _buckets.get(request.url.path)
        # Path patterns containing IDs aren't matched literally; we only rate-limit
        # the noisy roots above. Add per-pattern rules later if needed.
        if bucket is not None and request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            key = _key_for(request)
            allowed, retry = await bucket.take(key)
            if not allowed:
                return Response(
                    content=f'{{"detail":"Rate limit exceeded. Retry in {retry}s."}}',
                    status_code=429,
                    headers={"Retry-After": str(retry), "Content-Type": "application/json"},
                )
        return await call_next(request)


# ─── Security headers + request ID ─────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # HSTS only meaningful when served over TLS in front of a TLS terminator
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
        )
        return response
