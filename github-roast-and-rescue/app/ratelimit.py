"""A tiny per-visitor sliding-window limiter that protects the GitHub and Gemini quotas."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Record a request and say whether this visitor is still within the limit."""
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                return False
            hits.append(now)
            if len(self._hits) > 5000:                  # keep memory bounded
                for stale in [k for k, v in self._hits.items() if not v][:1000]:
                    del self._hits[stale]
            return True
