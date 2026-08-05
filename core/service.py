"""Service abstractions for AIOS-Core.

This module provides BaseService, Service Protocols and related types used by the
kernel, service manager and other core components.

Design goals:
- Abstract base class using abc.ABC for production-quality extension.
- All lifecycle methods are async.
- Use dataclasses and enums for clear, typed state.
- No business logic here; just lifecycle orchestration primitives.
"""
from __future__ import annotations

import abc
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


class ServiceStatus(Enum):
    """Service lifecycle states."""

    UNKNOWN = "unknown"
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"
    DEGRADED = "degraded"


@dataclass
class Health:
    """Health snapshot for a service.

    Attributes:
        status: Overall health status (ServiceStatus).
        details: Optional free-form details useful for diagnostics.
        checked_at: UTC timestamp when the health was evaluated.
    """

    status: ServiceStatus
    details: Optional[Dict[str, Any]] = None
    checked_at: datetime = field(default_factory=lambda: datetime.utcnow())


class Service(abc.ABC):
    """External-facing interface for services.

    Concrete services must implement all lifecycle methods. The kernel and
    service manager depend only on this interface (protocol).
    """

    id: UUID
    name: str
    version: str
    status: ServiceStatus
    dependencies: List[str]
    metrics: Dict[str, Any]

    @abc.abstractmethod
    async def start(self) -> None:
        """Start the service and transition its status to RUNNING.

        Implementations MUST be idempotent: calling start on an already-running
        service should be a no-op or a safe re-initialization.
        """

    @abc.abstractmethod
    async def stop(self) -> None:
        """Stop the service and transition its status to STOPPED.

        Implementations MUST be resilient and complete quickly; the manager
        will enforce a shutdown timeout.
        """

    @abc.abstractmethod
    async def restart(self) -> None:
        """Restart the service (stop then start)."""

    @abc.abstractmethod
    async def health(self) -> Health:
        """Return current health snapshot for the service."""


@dataclass
class BaseService(Service):
    """A small, production-minded base service implementation.

    Use this class as a starting point for concrete services inside the kernel.
    It implements sensible default behavior, state transitions, and simple
    metrics bookkeeping. No business logic is included.

    Fields:
        id: Unique identifier for the service (UUID4 by default).
        name: Logical name of the service (used for registry lookups).
        version: Semantic version string for the service.
        status: ServiceStatus representing current lifecycle state.
        dependencies: List of other service names this service depends on.
        metrics: Free-form metrics dictionary that implementations may update.
    """

    name: str
    version: str = "0.0.0"
    id: UUID = field(default_factory=uuid4)
    status: ServiceStatus = field(default=ServiceStatus.UNKNOWN)
    dependencies: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    # Internal lock to make lifecycle operations safe when called concurrently.
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def start(self) -> None:  # pragma: no cover - base behavior
        """Default start implementation.

        This implementation performs only state transitions and metrics updates.
        Subclasses should override and call super().start() if they need the
        state bookkeeping performed here.
        """
        async with self._lock:
            if self.status is ServiceStatus.RUNNING:
                return
            self.status = ServiceStatus.STARTING
            # small cooperative yield to let callers observe STARTING
            await asyncio.sleep(0)
            # update minimal metric
            self.metrics.setdefault("starts", 0)
            self.metrics["starts"] = self.metrics.get("starts", 0) + 1
            self.status = ServiceStatus.RUNNING

    async def stop(self) -> None:  # pragma: no cover - base behavior
        """Default stop implementation: set STOPPING -> STOPPED.

        Subclasses should perform resource cleanup then call super().stop().
        """
        async with self._lock:
            if self.status is ServiceStatus.STOPPED:
                return
            self.status = ServiceStatus.STOPPING
            await asyncio.sleep(0)
            self.metrics.setdefault("stops", 0)
            self.metrics["stops"] = self.metrics.get("stops", 0) + 1
            self.status = ServiceStatus.STOPPED

    async def restart(self) -> None:
        """Default restart implementation implemented via stop() and start().

        The method is safe for concurrent callers: it acquires the lifecycle lock
        and performs stop/start in sequence.
        """
        async with self._lock:
            # perform stop then start while holding lock to avoid interleaving.
            try:
                await self.stop()
            except Exception:
                # mark failed but continue to attempt start
                self.status = ServiceStatus.FAILED
            await self.start()

    async def health(self) -> Health:
        """Return a lightweight health snapshot.

        By default, health reflects the service status. Subclasses may extend
        the details field with richer diagnostics information.
        """
        status = (
            ServiceStatus.RUNNING
            if self.status is ServiceStatus.RUNNING
            else ServiceStatus.DEGRADED
        )
        details: Dict[str, Any] = {
            "status": self.status.value,
            "metrics": dict(self.metrics),
        }
        return Health(status=status, details=details)
