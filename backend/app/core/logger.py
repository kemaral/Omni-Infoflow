"""
Event Logger
=============
Collects ``NodeEvent`` objects emitted during pipeline execution and exposes
them via a simple in-memory ring buffer.  Consumers (API / WebSocket
handlers) can poll ``recent()`` or iterate ``stream()``.

A production upgrade path would swap the ring buffer for Redis Streams or
an async queue — but the interface stays the same.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import AsyncIterator

from app.models.workflow import NodeEvent


class EventBus:
    """Central hub for pipeline telemetry events.

    Usage::

        bus = EventBus(max_events=500)
        await bus.emit(NodeEvent(...))

        # API handler
        events = bus.recent(20)

        # WebSocket handler
        async for event in bus.stream():
            await ws.send_json(event.model_dump())
    """

    def __init__(self, max_events: int = 1000) -> None:
        self._buffer: deque[NodeEvent] = deque(maxlen=max_events)
        self._subscribers: list[asyncio.Queue[NodeEvent]] = []

    async def emit(self, event: NodeEvent) -> None:
        """Publish an event to the buffer and all active subscribers."""
        self._buffer.append(event)
        dead: list[asyncio.Queue[NodeEvent]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(queue)
        # Evict overflowed subscribers so they don't grow unbounded
        for q in dead:
            self._subscribers.remove(q)

    def recent(self, limit: int = 50) -> list[NodeEvent]:
        """Return the *limit* most recent events (newest last)."""
        items = list(self._buffer)
        return items[-limit:]

    async def stream(self) -> AsyncIterator[NodeEvent]:
        """Yield events as they arrive — designed for WebSocket consumers."""
        queue: asyncio.Queue[NodeEvent] = asyncio.Queue(maxsize=256)
        self._subscribers.append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    @property
    def total(self) -> int:
        return len(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()
