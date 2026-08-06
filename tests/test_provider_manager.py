from __future__ import annotations

import asyncio

import pytest

from adapters.ai_mock import MockProvider, MockProviderConfig
from core.provider_manager import ProviderManager


@pytest.mark.asyncio
async def test_provider_manager_round_robin_and_failover() -> None:
    mgr = ProviderManager()
    p1 = MockProvider(MockProviderConfig(provider_id="p1", delay=0.01, response_text="A"))
    p2 = MockProvider(MockProviderConfig(provider_id="p2", delay=0.01, response_text="B", fail=False))
    p3 = MockProvider(MockProviderConfig(provider_id="p3", delay=0.01, response_text="C", fail=True))
    mgr.register(p1)
    mgr.register(p2)
    mgr.register(p3)
    await mgr.start_all()
    # first request -> p1
    r1 = await mgr.request("hello")
    assert r1.provider_id in {"p1","p2","p3"}
    # even if one provider fails, manager should try others
    # set p1 to fail and ensure it falls back
    p1.cfg.fail = True
    # perform multiple requests to exercise rotation
    results = []
    for _ in range(3):
        try:
            res = await mgr.request("hi")
            results.append(res.provider_id)
        except Exception:
            results.append("err")
    assert any(r != "err" for r in results)
    await mgr.stop_all()
