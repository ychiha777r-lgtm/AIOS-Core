from __future__ import annotations

import asyncio
from typing import List

from core.secret_store import SecretStore
from core.provider_manager import ProviderManager


class ConnectionManager:
    """Manage lifecycle of SecretStore and ProviderManager (and other connectors).

    Starts/stops components and runs periodic healthchecks.
    """

    def __init__(self, secret_store: SecretStore, provider_manager: ProviderManager) -> None:
        self.secret_store = secret_store
        self.provider_manager = provider_manager
        self._health_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        await self.provider_manager.start_all()
        self._stop_event.clear()
        self._health_task = asyncio.create_task(self._health_loop())

    async def stop(self) -> None:
        if self._health_task:
            self._stop_event.set()
            await self._health_task
        await self.provider_manager.stop_all()

    async def _health_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(5)
                await self.provider_manager.healthcheck_all()
        except asyncio.CancelledError:
            return
