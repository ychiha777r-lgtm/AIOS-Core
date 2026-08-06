from __future__ import annotations

import asyncio
from collections import deque
from typing import Dict, Iterable, List, Optional

from core.ai_provider import AIProvider, ProviderResponse


class ProviderManager:
    """Manage multiple AIProvider instances and dispatch requests.

    Simple round-robin dispatcher with basic start/stop and healthcheck.
    """

    def __init__(self) -> None:
        self._providers: Dict[str, AIProvider] = {}
        self._order: deque[str] = deque()
        self._lock = asyncio.Lock()

    def register(self, provider: AIProvider) -> None:
        if provider.provider_id in self._providers:
            raise RuntimeError(f"provider {provider.provider_id} already registered")
        self._providers[provider.provider_id] = provider
        self._order.append(provider.provider_id)

    async def start_all(self) -> None:
        async with self._lock:
            await asyncio.gather(*(p.start() for p in self._providers.values()))

    async def stop_all(self) -> None:
        async with self._lock:
            await asyncio.gather(*(p.stop() for p in self._providers.values()))

    async def healthcheck_all(self) -> Dict[str, bool]:
        async with self._lock:
            results = await asyncio.gather(*(p.healthcheck() for p in self._providers.values()), return_exceptions=True)
            return {pid: bool(res) and not isinstance(res, Exception) for pid, res in zip(self._providers.keys(), results)}

    async def request(self, prompt: str, *, timeout: Optional[float] = None) -> ProviderResponse:
        """Dispatch to next provider in round-robin order.

        If provider raises, try next provider until exhausted.
        """
        async with self._lock:
            if not self._order:
                raise RuntimeError("no providers registered")
            tried: List[str] = []
            for _ in range(len(self._order)):
                pid = self._order[0]
                self._order.rotate(-1)
                tried.append(pid)
                provider = self._providers[pid]
                try:
                    coro = provider.request(prompt)
                    if timeout is not None:
                        res = await asyncio.wait_for(coro, timeout=timeout)
                    else:
                        res = await coro
                    return res
                except Exception:
                    # log in real impl; here we try next
                    continue
            raise RuntimeError(f"all providers failed: {tried}")

    def list_providers(self) -> Iterable[str]:
        return list(self._providers.keys())
