from __future__ import annotations

import asyncio
from typing import List, Optional

from core.secret_store import SecretStore
from core.provider_manager import ProviderManager
from core.service import Service, Health


class ConnectionManager:
    """Manage lifecycle of SecretStore, ProviderManager and additional services.

    This manager starts/stops the provider manager and any registered services
    (for example adapters like TelegramAdapter). It also runs a periodic
    healthcheck loop.
    """

    def __init__(self, secret_store: SecretStore, provider_manager: ProviderManager) -> None:
        self.secret_store = secret_store
        self.provider_manager = provider_manager
        self._services: List[Service] = []
        self._health_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def register_service(self, service: Service) -> None:
        """Register an additional service to be managed by the connection manager.

        Services registered here will be started after provider_manager.start_all()
        and stopped before provider_manager.stop_all(). Duplicate registration is
        ignored.
        """
        if service in self._services:
            return
        self._services.append(service)

    async def start(self) -> None:
        # Start providers first (they may be needed by services)
        await self.provider_manager.start_all()

        # Start all registered services
        if self._services:
            await asyncio.gather(*(s.start() for s in self._services))

        self._stop_event.clear()
        self._health_task = asyncio.create_task(self._health_loop())

    async def stop(self) -> None:
        # Stop health loop first
        if self._health_task:
            self._stop_event.set()
            await self._health_task

        # Stop registered services
        if self._services:
            await asyncio.gather(*(s.stop() for s in self._services))

        # Finally stop provider manager
        await self.provider_manager.stop_all()

    async def _health_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(5)
                # provider manager healthcheck
                try:
                    await self.provider_manager.healthcheck_all()
                except Exception:
                    # swallow errors from provider healthchecks; log in real impl
                    pass

                # services health (best-effort)
                for svc in list(self._services):
                    try:
                        # Some Service implementations may provide health(); call but ignore the result
                        if hasattr(svc, "health"):
                            h: Health = await svc.health()
                            # optionally process/aggregate h
                    except Exception:
                        # ignore individual service health errors
                        pass
        except asyncio.CancelledError:
            return
