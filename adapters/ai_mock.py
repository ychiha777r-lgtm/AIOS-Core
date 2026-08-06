from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.ai_provider import AIProvider, ProviderResponse


@dataclass
class MockProviderConfig:
    provider_id: str
    delay: float = 0.0
    fail: bool = False
    response_text: str = "mock-response"


class MockProvider(AIProvider):
    def __init__(self, cfg: MockProviderConfig) -> None:
        self.cfg = cfg
        self.provider_id = cfg.provider_id
        self._started = False

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False

    async def healthcheck(self, timeout: float | None = None) -> bool:
        # simple health: started and not configured to fail
        return self._started and not self.cfg.fail

    async def request(self, prompt: str, **kwargs) -> ProviderResponse:
        if not self._started:
            raise RuntimeError("provider not started")
        if self.cfg.delay:
            await asyncio.sleep(self.cfg.delay)
        if self.cfg.fail:
            raise RuntimeError("configured failure")
        return ProviderResponse(provider_id=self.provider_id, text=self.cfg.response_text, raw={"prompt": prompt})
