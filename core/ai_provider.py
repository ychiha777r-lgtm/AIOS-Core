from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ProviderResponse:
    provider_id: str
    text: str
    raw: Optional[Dict[str, Any]] = None


class AIProvider:
    """Minimal provider interface (sync-compatible async API).

    Adapters should subclass this and implement start/stop/healthcheck/request.
    """

    provider_id: str

    async def start(self) -> None:  # pragma: no cover - trivial
        return None

    async def stop(self) -> None:  # pragma: no cover - trivial
        return None

    async def healthcheck(self, timeout: float | None = None) -> bool:  # pragma: no cover
        return True

    async def request(self, prompt: str, **kwargs) -> ProviderResponse:
        raise NotImplementedError
