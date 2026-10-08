"""A small thread-safe in-memory cache with time-to-live, used to respect GitHub rate limits."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Hashable, Tuple


class TTLCache:
    """Least-recently-used cache whose entries expire after `ttl` seconds."""

    def __init__(self, ttl: float, max_items: int = 1024, clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl
        self._max_items = max_items
        self._clock = clock
        self._items: "OrderedDict[Hashable, Tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> Tuple[bool, Any]:
        """Return (hit, value). A stored None counts as a hit."""
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return False, None
            expires_at, value = entry
            if self._clock() >= expires_at:
                del self._items[key]
                return False, None
            self._items.move_to_end(key)
            return True, value

    def set(self, key: Hashable, value: Any) -> None:
        """Store a value, evicting the least recently used entry when full."""
        if self._ttl <= 0:
            return
        with self._lock:
            self._items[key] = (self._clock() + self._ttl, value)
            self._items.move_to_end(key)
            while len(self._items) > self._max_items:
                self._items.popitem(last=False)

    def get_or_set(self, key: Hashable, factory: Callable[[], Any]) -> Any:
        """Return the cached value, or compute it with `factory` and cache it.

        Exceptions raised by `factory` propagate and nothing is cached.
        """
        hit, value = self.get(key)
        if hit:
            return value
        value = factory()
        self.set(key, value)
        return value

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
