"""Async unit tests for MemoryPriorityQueue implementation.

Covers lifecycle, enqueue/dequeue semantics, priority & FIFO ordering,
blocking/non-blocking behavior, timeouts, purge/inspect, metrics and
concurrent producers/consumers.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from itertools import count
from typing import Set
from uuid import UUID

import pytest

from core.event_model import Event, EventPriority
from core.queue import QueueItem, QueueClosedError, QueueTimeoutError, QueueFullError
from core.queue_memory import MemoryPriorityQueue

_seq = count()


def _make_event(topic: str, priority: EventPriority = EventPriority.NORMAL) -> Event:
    return Event.create(type=topic, priority=priority, source="test")


def _make_item(topic: str, priority: EventPriority = EventPriority.NORMAL) -> QueueItem:
    ev = _make_event(topic, priority=priority)
    return QueueItem(event=ev, enqueued_at=datetime.now(timezone.utc), sequence=next(_seq), priority=priority)


@pytest.mark.asyncio
async def test_lifecycle_enqueue_before_start_and_dequeue_before_start():
    q = MemoryPriorityQueue(maxsize=10)
    # enqueue before explicit start should work (MemoryPriorityQueue.start is no-op)
    item = _make_item("kernel.start")
    await q.enqueue(item)
    # dequeue before start should return the item
    got = await q.dequeue()
    assert got.event.id == item.event.id

    # double start is safe
    await q.start()
    await q.start()

    # stop is idempotent
    await q.stop()
    await q.stop()

    # After stop, enqueue should raise QueueClosedError
    with pytest.raises(QueueClosedError):
        await q.enqueue(_make_item("after.stop"))

    # When stopped and empty, dequeue should raise QueueClosedError
    with pytest.raises(QueueClosedError):
        await q.dequeue(timeout=0.01)


@pytest.mark.asyncio
async def test_basic_enqueue_dequeue_and_metrics():
    q = MemoryPriorityQueue(maxsize=10)
    await q.start()
    item = _make_item("svc.update")
    snapshot_before = q.metrics_snapshot()
    assert snapshot_before.current_size == 0

    await q.enqueue(item)
    assert q.qsize() == 1

    got = await q.dequeue()
    assert got.event.id == item.event.id

    metrics = q.metrics_snapshot()
    assert metrics.enqueue_count >= 1
    assert metrics.dequeue_count >= 1

    await q.stop()


@pytest.mark.asyncio
async def test_priority_and_fifo_ordering():
    q = MemoryPriorityQueue(maxsize=10)
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

    # different priorities
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
async def test_bounded_capacity_and_non_blocking_enqueue_and_timeouts():
    q = MemoryPriorityQueue(maxsize=2)
    await q.start()
    await q.enqueue(_make_item("1"))
    await q.enqueue(_make_item("2"))
    # non-blocking should fail immediately when full
    with pytest.raises(QueueFullError):
        await q.enqueue(_make_item("3"), block=False)

    # blocking with timeout should raise QueueTimeoutError if no space freed
    with pytest.raises(QueueTimeoutError):
        await q.enqueue(_make_item("4"), block=True, timeout=0.05)

    # but if a consumer frees space the blocking enqueue completes
    async def delayed_consumer():
        await asyncio.sleep(0.05)
        await q.dequeue()

    task = asyncio.create_task(delayed_consumer())
    await q.enqueue(_make_item("5"), block=True, timeout=1.0)
    await task

    await q.stop()


@pytest.mark.asyncio
async def test_purge_and_inspect():
    q = MemoryPriorityQueue(maxsize=10)
    await q.start()
    await q.enqueue(_make_item("a"))
    await q.enqueue(_make_item("b"))
    insp = q.inspect()
    assert insp.qsize == 2
    assert insp.oldest is not None and insp.newest is not None

    await q.purge()
    assert q.qsize() == 0
    await q.stop()


@pytest.mark.asyncio
async def test_concurrent_producers_and_consumers_stress():
    total_producers = 12
    items_per_producer = 50
    total_items = total_producers * items_per_producer
    q = MemoryPriorityQueue(maxsize=1000)
    await q.start()

    produced_ids: Set[UUID] = set()
    consumed_ids: Set[UUID] = set()

    async def producer(pid: int):
        for i in range(items_per_producer):
            item = _make_item(f"p{pid}-{i}")
            produced_ids.add(item.event.id)
            await q.enqueue(item)

    async def consumer():
        while len(consumed_ids) < total_items:
            try:
                it = await q.dequeue(timeout=1.0)
            except QueueTimeoutError:
                continue
            consumed_ids.add(it.event.id)

    producers = [asyncio.create_task(producer(i)) for i in range(total_producers)]
    consumers = [asyncio.create_task(consumer()) for _ in range(5)]

    await asyncio.gather(*producers)

    # wait for consumers to finish consuming all items
    await asyncio.wait_for(asyncio.gather(*consumers), timeout=30.0)

    assert len(produced_ids) == total_items
    assert len(consumed_ids) == total_items
    assert produced_ids == consumed_ids

    await q.stop()
