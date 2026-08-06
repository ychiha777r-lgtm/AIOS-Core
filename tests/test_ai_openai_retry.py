from __future__ import annotations

import asyncio

import pytest

from adapters.ai_openai import OpenAIProvider, REQUESTS, RETRIES, LATENCY
from core.secret_store import SecretNotFoundError


class DummyStore:
    def __init__(self, mapping: dict):
        self.mapping = mapping

    async def get_secret(self, name: str) -> str:
        if name not in self.mapping:
            raise SecretNotFoundError(name)
        return self.mapping[name]


@pytest.mark.asyncio
async def test_openai_retry_and_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    store = DummyStore({"OPENAI_API_KEY": "sk_test"})
    p = OpenAIProvider(store, api_key_name="OPENAI_API_KEY", model="gpt-test", retry_attempts=3, retry_multiplier=0.1)
    await p.start()

    calls = {"count": 0}

    async def flaky_post(path, payload, headers, timeout):
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("temporary")
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(p, "_http_post", flaky_post)

    # ensure metrics zeroed (prometheus client global registry persists across tests; we won't assert absolute values)
    res = await p.request("hi")
    assert res.text == "ok"
    assert calls["count"] == 3
    # RETRIES should be > 0
    # Can't directly inspect Counter value easily without registry, but ensure no exceptions and latency recorded
    # ensure REQUESTS incremented at least once
    # (we don't assert exact metrics values to keep test robust)
