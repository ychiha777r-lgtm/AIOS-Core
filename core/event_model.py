"""Event model and related types for AIOS-Core.

This module defines immutable event representations, trace context, priorities
and lightweight event records for history. All types are fully typed and
intended for use across the EventBus and other infrastructure components.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4


class EventPriority(Enum):
    """Priority levels for events. Enum values are textual to avoid magic numbers.

    Ordering semantics: lower ordinal -> higher priority when enqueued.
    Use the enum for comparisons and mapping to queue priority values.
    """

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"


@dataclass(frozen=True)
class TraceContext:
    """Trace context carried with every event for observability and correlation.

    Attributes:
        trace_id: A globally unique trace identifier.
        correlation_id: An application-level correlation id for related flows.
        parent_id: Optional parent span or event id.
        span_id: Unique id for this span.
    """

    trace_id: str
    correlation_id: Optional[str] = None
    parent_id: Optional[UUID] = None
    span_id: Optional[str] = None


@dataclass(frozen=True)
class Event:
    """Immutable event that flows through the system.

    This dataclass is intentionally frozen to prevent accidental mutation by
    handlers or middleware. Middleware that needs to modify event content should
    create a new Event instance explicitly.

    Attributes:
        id: Unique event id (UUID).
        type: Topic / routing key using MQTT-like dot-separated tokens.
        timestamp: UTC timestamp for event creation.
        priority: EventPriority enum value.
        source: Optional source identifier (service/agent name).
        payload: Optional lightweight payload. Large payloads are discouraged.
        metadata: Optional metadata map for diagnostics (small key/value pairs).
        trace: TraceContext instance for correlation.
    """

    id: UUID
    type: str
    timestamp: datetime
    priority: EventPriority
    source: Optional[str]
    payload: Optional[Dict[str, Any]]
    metadata: Dict[str, Any]
    trace: TraceContext

    @staticmethod
    def create(
        *,
        type: str,
        priority: EventPriority = EventPriority.NORMAL,
        source: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trace: Optional[TraceContext] = None,
        id: Optional[UUID] = None,
    ) -> "Event":
        """Factory to create a new Event with sane defaults.

        This enforces UTC timestamps and generates missing ids / trace context.
        """
        if metadata is None:
            metadata = {}
        if trace is None:
            trace = TraceContext(trace_id=str(uuid4()))
        return Event(
            id=id or uuid4(),
            type=type,
            timestamp=datetime.now(timezone.utc),
            priority=priority,
            source=source,
            payload=payload,
            metadata=metadata,
            trace=trace,
        )


@dataclass(frozen=True)
class EventRecord:
    """Lightweight record for event history / diagnostics.

    Does not contain full payload to avoid storing sensitive or large data.
    """

    id: UUID
    type: str
    timestamp: datetime
    priority: EventPriority
    source: Optional[str]
    trace_id: str


@dataclass
class EventResult:
    """Outcome report for a delivered event.

    Attributes:
        success: Whether delivery to at least one subscriber succeeded.
        duration_seconds: Wall-clock duration for delivery attempts.
        handler_count: Number of handlers invoked.
        retry_count: Total retry attempts across handlers.
        delivery_count: Successful deliveries.
        errors: List of error messages captured.
    """

    success: bool = False
    duration_seconds: float = 0.0
    handler_count: int = 0
    retry_count: int = 0
    delivery_count: int = 0
    errors: list[str] = field(default_factory=list)
