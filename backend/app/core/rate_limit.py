"""Lightweight in-memory request throttling for the login endpoint.

This is deliberately dependency-free (no Redis) to match the project's
low-dependency posture, and is intended as *brute-force protection* for
``/auth/login``. Being in-process it only guards a single worker; for a
multi-worker/multi-host production deployment the same ``allow()`` interface
should be backed by a shared store (e.g. Redis). That boundary is documented
rather than hidden.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple


class SlidingWindowLimiter:
    """Allow up to ``max_attempts`` hits per key within a rolling window."""

    def __init__(self, max_attempts: int, window_seconds: float) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, *, now: Optional[float] = None) -> Tuple[bool, float]:
        """Record a hit for ``key``.

        Returns ``(allowed, retry_after_seconds)``. When ``allowed`` is False the
        hit is *not* recorded (so throttled attempts don't extend the lockout)
        and ``retry_after`` is how long until a slot frees.
        """
        ts = time.monotonic() if now is None else now
        window_start = ts - self.window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= window_start:
                bucket.popleft()
            if len(bucket) >= self.max_attempts:
                retry_after = self.window_seconds - (ts - bucket[0])
                return False, max(retry_after, 0.0)
            bucket.append(ts)
            return True, 0.0

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


def client_identity(host: str, email: str) -> str:
    """A stable bucket key combining client IP + the account being tried.

    Scoping by both means a distributed attacker hammering many accounts is
    still bounded per-account, and one noisy IP can't lock out unrelated users.
    """
    return f"{host}|{email.strip().lower()}"
