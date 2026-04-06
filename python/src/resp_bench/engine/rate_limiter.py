"""Token bucket rate limiter."""

import asyncio
import time
import threading


class RateLimiter:
    """Leaky bucket rate limiter for sync use."""

    def __init__(self, rate_per_second: int):
        self._rate = rate_per_second
        if rate_per_second > 0:
            self._interval_ns = 1_000_000_000 // rate_per_second
        else:
            self._interval_ns = 0
        self._next_ns = time.monotonic_ns()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        if self._rate <= 0:
            return
        with self._lock:
            now = time.monotonic_ns()
            if now < self._next_ns:
                time.sleep((self._next_ns - now) / 1_000_000_000)
            self._next_ns = max(now, self._next_ns) + self._interval_ns


class AsyncRateLimiter:
    """Leaky bucket rate limiter for async use."""

    def __init__(self, rate_per_second: int):
        self._rate = rate_per_second
        if rate_per_second > 0:
            self._interval_ns = 1_000_000_000 // rate_per_second
        else:
            self._interval_ns = 0
        self._next_ns = time.monotonic_ns()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self._rate <= 0:
            return
        async with self._lock:
            now = time.monotonic_ns()
            if now < self._next_ns:
                await asyncio.sleep((self._next_ns - now) / 1_000_000_000)
            self._next_ns = max(now, self._next_ns) + self._interval_ns
