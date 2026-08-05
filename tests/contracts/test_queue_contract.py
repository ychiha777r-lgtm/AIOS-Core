"""Contract tests for any QueueInterface implementation.

These tests exercise the public QueueInterface contract and must not
import concrete implementations. An external conftest should provide the
`queue_factory` fixture which returns a Callable to create a fresh queue
instance for each test.

Contract tests MUST remain implementation-agnostic so that future adapters
(e.g., RedisQueue, KafkaQueue) can reuse the same suite.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from itertools import count
from typing import Callable

import pytest

from core.event_model import Event, EventPriority
from core.queue import QueueItem, QueueClosedError, QueueTimeoutError, QueueFullError, QueueInterface

_seq = count()


def _make_event(topic: str, priority: EventPriority = EventPriority.NORMAL) -> Event:
    return Event.create(type=topic, priority=priority, source="contract")


def _make_item(topic: str, priority: EventPriority = EventPriority.NORMAL) -> QueueItem:
    ev = _make_event(topic, priority=priority)
    return QueueItem(event=ev, enqueued_at=datetime.now(timezone.utc), sequence=next(_seq), priority=priority)


@pytest.fixture
def queue_factory() -> Callable[..., QueueInterface]:
    """Placeholder fixture. A test runner should override this in conftest to
    provide a concrete queue factory that returns a new QueueInterface instance.
    """
    raise pytest.skip("queue_factory fixture must be provided by the test runner")


@pytest.mark.asyncio
async def test_contract_lifecycle(queue_factory: Callable[..., QueueInterface]) -> None:
    q = queue_factory(maxsize=10)
    # start/stop idempotence
    await q.start()
    await q.start()
    await q.stop()
    await q.stop()


@pytest.mark.asyncio
async def test_contract_enqueue_dequeue_basic(queue_factory: Callable[..., QueueInterface]) -> None:
    q = queue_factory(maxsize=10)
    await q.start()
    item = _make_item("contract.basic")
    await q.enqueue(item)
    got = await q.dequeue()
    assert got.event.id == item.event.id
    await q.stop()


@pytest.mark.asyncio
async def test_contract_ordering_and_fifo(queue_factory: Callable[..., QueueInterface]) -> None:
    q = queue_factory(maxsize=20)
    await q.start()
    a = _make_item("A", priority=EventPriority.NORMAL)
    b = _make_item("B", priority=EventPriority.NORMAL)
    c = _make_item("C", priority=EventPriority.NORMAL)
    await q.enqueue(a)
    await q.enqueue(b)
    await q.enqueue(c)
    assert (await q.dequeue()).event.id == a.event.id
    assert (await q.dequeue()).event.id == b.event.id
    assert (await q.dequeue()).event.id == c.event.id

    # priority ordering
    low = _make_item("low", priority=EventPriority.LOW)
    critical = _make_item("crit", priority=EventPriority.CRITICAL)
    normal = _make_item("norm", priority=EventPriority.NORMAL)
    await q.enqueue(low)
    await q.enqueue(critical)
    await q.enqueue(normal)
    first = await q.dequeue()
    second = await q.dequeue()
    third = await q.dequeue()
    assert first.event.priority == EventPriority.CRITICAL
    assert second.event.priority == EventPriority.NORMAL
    assert third.event.priority == EventPriority.LOW
    await q.stop()


@pytest.mark.asyncio
async def test_contract_capacity_and_timeouts(queue_factory: Callable[..., QueueInterface]) -> None:
    q = queue_factory(maxsize=2)
    await q.start()
    await q.enqueue(_make_item("1"))
    await q.enqueue(_make_item("2"))
    with pytest.raises(QueueFullError):
        await q.enqueue(_make_item("3"), block=False)
    with pytest.raises(QueueTimeoutError):
        await q.enqueue(_make_item("4"), block=True, timeout=0.05)
    await q.stop()


@pytest.mark.asyncio
async def test_contract_shutdown_behavior(queue_factory: Callable[..., QueueInterface]) -> None:
    q = queue_factory(maxsize=10)
    await q.start()
    await q.enqueue(_make_item("x"))
    await q.stop()
    # dequeue should allow draining and then raise on empty
    got = await q.dequeue()
    assert got
    with pytest.raises(QueueClosedError):
        await q.dequeue(timeout=0.01)


@pytest.mark.asyncio
async def test_contract_inspect_purge_metrics(queue_factory: Callable[..., QueueInterface]) -> None:
    q = queue_factory(maxsize=10)
    await q.start()
    await q.enqueue(_make_item("i1"))
    await q.enqueue(_make_item("i2"))
    insp = q.inspect()
    assert insp.qsize >= 0
    # purge empties
    await q.purge()
    assert q.qsize() == 0
    # metrics_snapshot may be implementation-specific; ensure presence if offered
    if hasattr(q, "metrics_snapshot"):
        ms = q.metrics_snapshot()  # type: ignore[attr-defined]
        assert hasattr(ms, "enqueue_count")
        assert hasattr(ms, "dequeue_count")
    await q.stop()
