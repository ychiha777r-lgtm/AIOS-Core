from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from adapters.ai_openai import OpenAIProvider
from core.secret_store import SecretStore, SecretNotFoundError
from core.ai_provider import ProviderResponse


class FakeSecretStore(SecretStore):
    def __init__(self, mapping: Dict[str, str]) -> None:
        self._mapping = mapping

    async def get_secret(self, name: str) -> str:
        if name not in self._mapping:
            raise SecretNotFoundError(name)
        return self._mapping[name]

    async def set_secret(self, name: str, value: str) -> None:
        self._mapping[name] = value

    async def list_secrets(self):
        return list(self._mapping.keys())

    async def rotate_secret(self, name: str, new_value: str) -> None:
        await self.set_secret(name, new_value)


@pytest.mark.asyncio
async def test_openai_provider_start_and_request(monkeypatch: pytest.MonkeyPatch) -> None:
    store = FakeSecretStore({"OPENAI_API_KEY": "sk_test"})
    provider = OpenAIProvider(store, api_key_name="OPENAI_API_KEY", model="gpt-test")
    await provider.start()
    assert provider._api_key == "sk_test"

    # monkeypatch the _http_post to avoid network
    async def fake_post(path: str, json_payload: Dict[str, Any], headers: Dict[str, str], timeout: float | None):
        return {"choices": [{"message": {"content": "hello from mock"}}]}

    monkeypatch.setattr(provider, "_http_post", fake_post)

    res = await provider.request("hello")
    assert isinstance(res, ProviderResponse)
    assert res.text == "hello from mock"


@pytest.mark.asyncio
async def test_openai_provider_missing_key_raises() -> None:
    store = FakeSecretStore({})
    provider = OpenAIProvider(store, api_key_name="OPENAI_API_KEY")
    with pytest.raises(RuntimeError):
        await provider.start()
