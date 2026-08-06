from __future__ import annotations

import asyncio
import os
import types
from typing import List

import pytest

from adapters.secret_env import EnvSecretStore


@pytest.mark.asyncio
async def test_env_secret_store_set_get_list_rotate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_TEST", raising=False)
    store = EnvSecretStore()
    await store.set_secret("SECRET_TEST", "value123")
    got = await store.get_secret("SECRET_TEST")
    assert got == "value123"
    keys = list([k async for k in store.list_secrets()]) if False else list(store.list_secrets())
    # keys may include many env vars; ensure ours present
    assert "SECRET_TEST" in keys or any(k == "SECRET_TEST" for k in keys)
    await store.rotate_secret("SECRET_TEST", "new")
    assert await store.get_secret("SECRET_TEST") == "new"
