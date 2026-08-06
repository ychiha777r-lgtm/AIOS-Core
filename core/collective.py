from __future__ import annotations

import asyncio
from collections import Counter
from typing import Dict, List

from core.ai_provider import ProviderResponse
from core.provider_manager import ProviderManager


class CollectiveManager:
    """Coordinate multiple providers to produce a collective decision.

    Simple ensemble strategy: send prompt to N providers in parallel and apply
    majority vote on returned text. Extensible with pluggable strategies.
    """

    def __init__(self, provider_manager: ProviderManager) -> None:
        self.providers = provider_manager

    async def ensemble_vote(self, prompt: str, providers: List[str] | None = None, timeout: float | None = None) -> ProviderResponse:
        if providers is None:
            providers = list(self.providers.list_providers())
        coros = [self.providers._providers[pid].request(prompt) for pid in providers]
        results = []
        for coro in asyncio.as_completed(coros, timeout=timeout):
            try:
                res = await coro
                results.append(res)
            except Exception:
                # ignore failed provider for ensemble
                continue
        if not results:
            raise RuntimeError("no provider responses")
        texts = [r.text for r in results]
        most_common = Counter(texts).most_common(1)[0][0]
        # pick first provider that returned the chosen text
        chosen = next(r for r in results if r.text == most_common)
        return chosen
