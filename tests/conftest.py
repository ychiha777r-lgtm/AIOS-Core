"""Pytest conftest for integration and contract tests.

Provides fixtures used across tests. The queue_factory fixture adapts the
MemoryPriorityQueue for the contract test suite. For future adapters, this
file can be overridden in CI or by downstream test runners.
"""
from __future__ import annotations

from typing import Callable

import pytest

from core.queue_memory import MemoryPriorityQueue
from core.queue import QueueInterface


@pytest.fixture
def queue_factory() -> Callable[..., QueueInterface]:
    """Return a factory that creates a new QueueInterface implementation.

    The factory accepts keyword arguments passed to the concrete constructor.
    For the contract tests this keeps them implementation-agnostic while
    allowing the test runner to swap in other implementations.
    """

    def _factory(*, maxsize: int = 0) -> QueueInterface:
        return MemoryPriorityQueue(maxsize=maxsize)

    return _factory
