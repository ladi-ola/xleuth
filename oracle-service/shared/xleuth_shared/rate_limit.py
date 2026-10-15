"""Task 16: per-IP sliding-window rate limits + request size guard.

No new dependencies (Starlette is imported lazily so plain-shared users are
unaffected). Both FastAPI services wire this in their app factory; rules are
env-tunable. Faucet keeps its own 24h per-wallet cooldown on top.
"""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass


@dataclass
class Rule:
    path_prefix: str
    methods: tuple[str, ...]
    limit: int
    window_s: int
    key_by_wallet: bool = False


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str, limit: int, window_s: int, now: float | None = None) -> tuple[bool, float]:
        """(allowed, retry_after_s). Prunes expired entries on each call."""
        now = now if now is not None else time.monotonic()
        dq = self._hits.setdefault(key, deque())
        cutoff = now - window_s
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) >= limit:
            return False, max(0.0, dq[0] + window_s - now)
        dq.append(now)
        return True, 0.0


def rules_from_env(service: str) -> list[Rule]:
    """Env-tunable rules. Defaults are DECISION-MADE values (see QA report)."""
    if service == "backend-api":
        return [
            Rule("/auth/verify", ("POST",),
                 int(os.getenv("RL_AUTH_VERIFY_PER_MIN", "30")), 60),
            Rule("/faucet/claim", ("POST",),
                 int(os.getenv("RL_FAUCET_PER_MIN", "10")), 60),
        ]
    if service == "matching-engine":
        return [
            Rule("/orders", ("POST",),
                 int(os.getenv("RL_ORDERS_PER_MIN", "120")), 60),
        ]
    return []


MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", str(1_000_000)))


def _client_ip(request) -> str:
    if os.getenv("TRUST_PROXY", "0") == "1":
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware:
    """Pure-Starlette middleware (no FastAPI import needed)."""

    def __init__(self, app, service: str, limiter: SlidingWindowLimiter | None = None,
                 rules: list[Rule] | None = None, max_body_bytes: int = MAX_BODY_BYTES):
        from starlette.middleware.base import BaseHTTPMiddleware

        class _Inner(BaseHTTPMiddleware):
            async def dispatch(inner_self, request, call_next):
                return await self._handle(request, call_next)

        self._inner = _Inner(app)
        self.rules = rules if rules is not None else rules_from_env(service)
        self.limiter = limiter or SlidingWindowLimiter()
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        return await self._inner(scope, receive, send)

    async def _handle(self, request, call_next):
        from starlette.responses import JSONResponse

        try:
            length = int(request.headers.get("content-length", "0") or 0)
        except ValueError:
            length = 0
        if length > self.max_body_bytes:
            return JSONResponse({"detail": "request_too_large"}, status_code=413)

        for rule in self.rules:
            if request.method in rule.methods and request.url.path.startswith(rule.path_prefix):
                key = f"{rule.path_prefix}:{_client_ip(request)}"
                ok, retry = self.limiter.allow(key, rule.limit, rule.window_s)
                if not ok:
                    return JSONResponse(
                        {"detail": "rate_limited", "retry_after": int(retry) + 1},
                        status_code=429,
                        headers={"Retry-After": str(int(retry) + 1)},
                    )
        return await call_next(request)
