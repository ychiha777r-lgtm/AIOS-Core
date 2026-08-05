"""Queue abstraction and shared types for AIOS-Core event transport layer.

This module defines the QueueInterface and related data types used by the
EventBus. Implementations must provide async enqueue/dequeue semantics and
must not expose underlying concurrency primitives to callers.
"""
from __future__ import annotations

import abc
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from typing import Optional, Protocol
from uuid import UUID

from core.event_model import Event, EventPriority, EventRecord
from core.exceptions import EventBusError, QueueFullError


class QueueError(EventBusError):
    """Base queue error."""


class QueueClosedError(QueueError):
    """Raised when an operation is attempted on a closed queue."""


class QueueTimeoutError(QueueError):
    """Raised when a queue operation times out."""


@dataclass(frozen=True)
class QueueItem:
    """Item placed on the queue for delivery.

    Attributes:
        event: The immutable Event instance.
        enqueued_at: UTC timestamp when the item was enqueued.
        sequence: Monotonic sequence number assigned by producer/queue.
        priority: EventPriority used for ordering.
        attempts: Number of delivery attempts so far (managed by EventBus).
    """

    event: Event
    enqueued_at: datetime
    sequence: int
    priority: EventPriority
    attempts: int = 0


@dataclass(frozen=True)
class QueueRecord:
    """Lightweight diagnostic record representing an item in the queue.

    This intentionally omits full payload for safety and diagnostic use only.
    """

    event_id: UUID
    type: str
    enqueued_at: datetime
    priority: EventPriority
    source: Optional[str]


@dataclass(frozen=True)
class QueueInspection:
    """Snapshot view of queue diagnostics."""

    qsize: int
    maxsize: int
    oldest: Optional[QueueRecord]
    newest: Optional[QueueRecord]


class QueueInterface(abc.ABC):
    """Abstract interface for queues used by the EventBus.

    Implementations must be fully async and enforce bounded capacity semantics
    when maxsize > 0.
    """

    @abc.abstractmethod
    async def start(self) -> None:
        """Prepare internal resources. Called before use.

        Implementations may spawn background tasks if required.
        """

    @abc.abstractmethod
    async def stop(self) -> None:
        """Stop the queue and wake any waiting producers/consumers.

        After stop() the queue must refuse new enqueues (raise QueueClosedError).
        Dequeue operations should continue to drain until empty and then raise
        QueueClosedError.
        """

    @abc.abstractmethod
    async def enqueue(self, item: QueueItem, *, block: bool = True, timeout: Optional[float] = None) -> None:
        """Enqueue an item.

        Args:
            item: QueueItem to enqueue.
            block: If True, wait until space is available (subject to timeout).
                   If False, raise QueueFullError immediately when full.
            timeout: Optional timeout in seconds for blocking wait.
        """

    @abc.abstractmethod
    async def dequeue(self, *, timeout: Optional[float] = None) -> QueueItem:
        """Dequeue an item, waiting up to timeout seconds.

        When the queue is stopped and empty, implementations should raise
        QueueClosedError.
        """

    @abc.abstractmethod
    def qsize(self) -> int:
        """Return current approximate queue size."""

    @abc.abstractmethod
    def maxsize(self) -> int:
        """Return configured maximum size (0 implies unbounded)."""

    @abc.abstractmethod
    def is_closed(self) -> bool:
        """Return True if the queue has been stopped."""

    @abc.abstractmethod
    def inspect(self) -> QueueInspection:
        """Return a lightweight inspection snapshot."""

    @abc.abstractmethod
    async def purge(self) -> None:
        """Remove all items from the queue."""
