"""Memory-backed priority queue for AIOS-Core.

This implementation adheres to the QueueInterface contract defined in
core/queue.py and is intended as the first concrete queue backend.

Design guarantees:
- Bounded capacity (maxsize > 0).
- Priority ordering based on EventPriority with FIFO for same-priority using
  per-item sequence numbers.
- Async-safe methods; no direct exposure of asyncio primitives.
- Deterministic behavior suitable for production use.
"""
from __future__ import annotations

import asyncio
import heapq
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from typing import List, Optional, Tuple

from core.event_model import EventPriority
from core.queue import (
    QueueInterface,
    QueueItem,
    QueueInspection,
    QueueRecord,
    QueueClosedError,
    QueueFullError,
    QueueTimeoutError,
)


_LOGGER = logging.getLogger("aios.queue.memory")

_PRIORITY_MAP = {
    EventPriority.CRITICAL: 0,
    EventPriority.HIGH: 1,
    EventPriority.NORMAL: 2,
    EventPriority.LOW: 3,
    EventPriority.BACKGROUND: 4,
}


@dataclass
class QueueMetricsSnapshot:
    enqueue_count: int
    dequeue_count: int
    drop_count: int
    current_size: int
    max_size: int


class MemoryPriorityQueue(QueueInterface):
    """In-memory priority queue implementing QueueInterface.

    Notes:
        - Sequence numbers are taken from QueueItem.sequence for FIFO behavior.
        - No global counters; all state is instance-local.
    """

    def __init__(self, maxsize: int = 0) -> None:
        """Create a new MemoryPriorityQueue.

        Args:
            maxsize: Maximum number of items in the queue. 0 means unbounded.
        """
        self._maxsize = int(maxsize)
        self._heap: List[Tuple[int, int, QueueItem]] = []
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Condition(lock=self._lock)
        self._not_full = asyncio.Condition(lock=self._lock)
        self._closed = False

        # metrics
        self._enqueue_count = 0
        self._dequeue_count = 0
        self._drop_count = 0

        # local monotonic counter for diagnostics (not user-facing)
        self._local_seq = count()

    async def start(self) -> None:
        """Start the queue (no-op for memory-backed queue)."""
        _LOGGER.debug("MemoryPriorityQueue.start called")

    async def stop(self) -> None:
        """Stop the queue and wake any waiters. After stop, enqueues are rejected."""
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            self._not_empty.notify_all()
            self._not_full.notify_all()
        _LOGGER.info("MemoryPriorityQueue stopped")

    async def enqueue(self, item: QueueItem, *, block: bool = True, timeout: Optional[float] = None) -> None:
        """Enqueue an item with optional blocking behavior.

        Raises:
            QueueClosedError: if the queue is closed.
            QueueFullError: if the queue is full and block==False or timeout expires.
        """
        priority_index = _PRIORITY_MAP[item.priority]
        async with self._lock:
            if self._closed:
                raise QueueClosedError("Queue is closed for enqueues")

            if self._maxsize > 0:
                # wait until there is space or timeout
                if len(self._heap) >= self._maxsize:
                    if not block:
                        self._drop_count += 1
                        raise QueueFullError("Queue is full (non-blocking)")

                    def _space_available() -> bool:  # noqa: D401 - small inner predicate
                        return len(self._heap) < self._maxsize or self._closed

                    got_space = await self._not_full.wait_for(_space_available, timeout=timeout)
                    if not got_space:
                        self._drop_count += 1
                        raise QueueTimeoutError("Timeout while waiting for queue space")
                    if self._closed:
                        raise QueueClosedError("Queue was closed while waiting for space")

            # push to heap: (priority_index, sequence, item)
            heapq.heappush(self._heap, (priority_index, item.sequence, item))
            self._enqueue_count += 1
            # notify consumers
            self._not_empty.notify()
            _LOGGER.debug("Enqueued event %s (priority=%s, seq=%d)", item.event.id, item.priority, item.sequence)

    async def dequeue(self, *, timeout: Optional[float] = None) -> QueueItem:
        """Dequeue the highest-priority item, waiting up to timeout seconds.

        Raises:
            QueueClosedError: when the queue is closed and empty.
            QueueTimeoutError: when timeout expires while waiting and queue is still empty.
        """
        async with self._lock:
            if not self._heap and self._closed:
                raise QueueClosedError("Queue closed and empty")

            if not self._heap:
                # wait for an item or closed state
                def _has_item() -> bool:
                    return bool(self._heap) or self._closed

                available = await self._not_empty.wait_for(_has_item, timeout=timeout)
                if not available:
                    raise QueueTimeoutError("Timeout while waiting for an item")
                if not self._heap and self._closed:
                    raise QueueClosedError("Queue closed and empty")

            # pop the best element
            priority_index, seq, item = heapq.heappop(self._heap)
            self._dequeue_count += 1
            # notify producers waiting for space
            self._not_full.notify()
            _LOGGER.debug("Dequeued event %s (priority_index=%d, seq=%d)", item.event.id, priority_index, seq)
            return item

    def qsize(self) -> int:
        return len(self._heap)

    def maxsize(self) -> int:
        return self._maxsize

    def is_closed(self) -> bool:
        return self._closed

    def inspect(self) -> QueueInspection:
        """Return a lightweight snapshot of queue diagnostics."""
        # build QueueRecord for oldest and newest by scanning heap
        if not self._heap:
            oldest = newest = None
        else:
            # heap is not ordered by sequence for all priorities; derive records
            items = [entry[2] for entry in self._heap]
            # find min and max by enqueued timestamp
            oldest_item = min(items, key=lambda i: i.enqueued_at)
            newest_item = max(items, key=lambda i: i.enqueued_at)
            oldest = QueueRecord(
                event_id=oldest_item.event.id,
                type=oldest_item.event.type,
                enqueued_at=oldest_item.enqueued_at,
                priority=oldest_item.priority,
                source=oldest_item.event.source,
            )
            newest = QueueRecord(
                event_id=newest_item.event.id,
                type=newest_item.event.type,
                enqueued_at=newest_item.enqueued_at,
                priority=newest_item.priority,
                source=newest_item.event.source,
            )
        return QueueInspection(qsize=self.qsize(), maxsize=self._maxsize, oldest=oldest, newest=newest)

    async def purge(self) -> None:
        """Remove all items from the queue."""
        async with self._lock:
            self._heap.clear()
            self._not_full.notify_all()
            _LOGGER.info("Queue purged")

    def metrics_snapshot(self) -> QueueMetricsSnapshot:
        """Return a snapshot of queue metrics."""
        return QueueMetricsSnapshot(
            enqueue_count=self._enqueue_count,
            dequeue_count=self._dequeue_count,
            drop_count=self._drop_count,
            current_size=self.qsize(),
            max_size=self._maxsize,
        )
