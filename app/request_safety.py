from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request


class FixedWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, bucket: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        now = time.monotonic()
        event_key = (key, bucket)
        with self._lock:
            events = self._events[event_key]
            while events and events[0] <= now - window_seconds:
                events.popleft()
            if len(events) >= limit:
                return False, max(1, int(window_seconds - (now - events[0])))
            events.append(now)
            return True, 0


limiter = FixedWindowLimiter()


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",", 1)[0].strip() if forwarded else request.client.host if request.client else "unknown"


def rate_limit_for(path: str, method: str) -> tuple[str, int] | None:
    if method != "POST":
        return None
    if path in {
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/forgot-password",
        "/api/v1/auth/reset-password",
        "/api/v1/auth/refresh",
        "/api/v1/auth/google",
    }:
        return "auth", 60
    if path.startswith("/api/v1/ai"):
        return "ai", 30
    if path == "/api/v1/admin/exam-imports" or path.endswith("/retry"):
        return "import", 10
    if path.endswith("/start") or path.endswith("/submit"):
        return "exam", 20
    return None
