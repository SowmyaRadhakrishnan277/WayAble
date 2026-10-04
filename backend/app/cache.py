"""Bounded async TTL cache for rate-limited public map providers."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import TypeVar


T = TypeVar("T")


class AsyncTTLCache:
    """Caches provider responses and coalesces duplicate in-flight requests."""

    def __init__(self, max_entries: int = 512) -> None:
        self._max_entries = max_entries
        self._values: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self._in_flight: dict[str, asyncio.Task[object]] = {}
        self._lock = asyncio.Lock()

    async def get_or_load(self, key: str, ttl_seconds: int, loader: Callable[[], Awaitable[T]]) -> T:
        now = time.monotonic()
        async with self._lock:
            cached = self._values.get(key)
            if cached and cached[0] > now:
                self._values.move_to_end(key)
                return cached[1]  # type: ignore[return-value]

            task = self._in_flight.get(key)
            if task is None:
                task = asyncio.create_task(loader())
                self._in_flight[key] = task

        try:
            value = await task
        except Exception:
            async with self._lock:
                self._in_flight.pop(key, None)
            raise

        async with self._lock:
            self._in_flight.pop(key, None)
            self._values[key] = (time.monotonic() + ttl_seconds, value)
            self._values.move_to_end(key)
            while len(self._values) > self._max_entries:
                self._values.popitem(last=False)
        return value  # type: ignore[return-value]
