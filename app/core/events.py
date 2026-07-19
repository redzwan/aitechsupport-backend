"""In-process pub/sub for realtime fan-out (single-worker).

Publishers are sync request handlers (running in the anyio threadpool); subscribers
are async SSE generators (on the event loop). `publish()` is thread-safe — it hops
onto the loop via `call_soon_threadsafe`. Behind this small interface a Redis-backed
bus can be swapped in for multi-worker safety (see AGENT_APPS_SCOPE.md, Phase 3);
until then this is correct because prod runs a single uvicorn worker.

Delivery is best-effort: a slow subscriber's queue overflows -> events are dropped,
and the client recovers by catching up from the DB on its next (re)connect. The
stream is a latency optimization, never the source of truth.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None

    def _ensure_loop(self) -> None:
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

    async def subscribe(self, topic: str) -> asyncio.Queue:
        self._ensure_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subs[topic].add(q)
        return q

    def unsubscribe(self, topic: str, q: asyncio.Queue) -> None:
        subs = self._subs.get(topic)
        if subs:
            subs.discard(q)
            if not subs:
                self._subs.pop(topic, None)

    def publish(self, topic: str, data: dict) -> None:
        """Thread-safe: enqueue to every subscriber of `topic`. No-op if nobody is
        listening or the loop isn't running yet."""
        loop = self._loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._deliver, topic, data)
        except RuntimeError:
            pass  # loop closed during shutdown

    def _deliver(self, topic: str, data: dict) -> None:
        for q in list(self._subs.get(topic, ())):
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass  # slow consumer -> drop; it catches up from the DB


bus = EventBus()


def conv_topic(conv_id: int) -> str:
    return f"conv:{conv_id}"


def org_topic(org_id: int) -> str:
    return f"org:{org_id}"
