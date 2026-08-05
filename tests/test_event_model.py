"""Unit tests for core.event_model module.

Tests cover Event creation, immutability, TraceContext, EventPriority,
EventRecord and EventResult behaviors.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from uuid import UUID

import pytest

from core.event_model import Event, TraceContext, EventPriority, EventRecord, EventResult


def test_event_create_defaults() -> None:
    ev = Event.create(type="kernel.start")
    assert isinstance(ev.id, UUID)
    assert ev.type == "kernel.start"
    assert ev.timestamp.tzinfo is not None and ev.timestamp.tzinfo.utcoffset(ev.timestamp) is not None
    assert ev.priority == EventPriority.NORMAL
    assert isinstance(ev.trace, TraceContext)


def test_event_immutability() -> None:
    ev = Event.create(type="service.update")
    with pytest.raises(dataclasses.FrozenInstanceError):
        # attempt to mutate a frozen dataclass should raise
        ev.type = "service.changed"


def test_trace_context_fields() -> None:
    trace = TraceContext(trace_id="trace-123", correlation_id="corr-1")
    ev = Event.create(type="agent.run", trace=trace)
    assert ev.trace.trace_id == "trace-123"
    assert ev.trace.correlation_id == "corr-1"


def test_event_record_and_result() -> None:
    ev = Event.create(type="memory.updated", source="mem.svc")
    rec = EventRecord(
        id=ev.id,
        type=ev.type,
        timestamp=ev.timestamp,
        priority=ev.priority,
        source=ev.source,
        trace_id=ev.trace.trace_id,
    )
    assert rec.id == ev.id
    result = EventResult(success=True, duration_seconds=0.01, handler_count=1, delivery_count=1)
    assert result.success
    assert result.delivery_count == 1
