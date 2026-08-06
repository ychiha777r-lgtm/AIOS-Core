from __future__ import annotations

import pytest

from adapters.ai_mock import MockProvider, MockProviderConfig
from core.collective import CollectiveManager
from core.provider_manager import ProviderManager


@pytest.mark.asyncio
async def test_ensemble_vote_majority() -> None:
    mgr = ProviderManager()
    mgr.register(MockProvider(MockProviderConfig(provider_id="p1", response_text="YES")))
    mgr.register(MockProvider(MockProviderConfig(provider_id="p2", response_text="NO")))
    mgr.register(MockProvider(MockProviderConfig(provider_id="p3", response_text="YES")))
    await mgr.start_all()
    coll = CollectiveManager(mgr)
    res = await coll.ensemble_vote("ask")
    assert res.text == "YES"
    await mgr.stop_all()
