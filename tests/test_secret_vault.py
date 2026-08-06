from __future__ import annotations

import httpx

import pytest

from adapters.secret_vault import VaultSecretStore, VaultError
from core.secret_store import SecretNotFoundError


@pytest.mark.asyncio
async def test_vault_secret_store_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mock httpx AsyncClient.get to return expected JSON
    class FakeResponse:
        def __init__(self, json_data, status=200):
            self._json = json_data
            self.status_code = status

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("err", request=None, response=types.SimpleNamespace(status_code=self.status_code))

        async def json(self):
            return self._json

    async def fake_get(self, url, headers=None, timeout=None):
        # URL ends with /openai/KEY
        if url.endswith("/openai/KEY") or url.endswith("/openai/KEY"):
            return types.SimpleNamespace(json=lambda: {"data": {"data": {"value": "s3cr3t"}}}, status_code=200)
        return types.SimpleNamespace(json=lambda: {}, status_code=404)

    # Instead of patching httpx.AsyncClient.get directly (which is a coroutine function),
    # we will monkeypatch adapters.secret_vault.httpx.AsyncClient to a dummy class
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None, timeout=None):
            if url.endswith("/openai/KEY"):
                class R:
                    status_code = 200

                    def raise_for_status(self):
                        return None

                    def json(self):
                        return {"data": {"data": {"value": "s3cr3t"}}}

                return R()
            class R404:
                status_code = 404

                def raise_for_status(self):
                    raise httpx.HTTPStatusError("not found", request=None, response=types.SimpleNamespace(status_code=404))

                def json(self):
                    return {}

            return R404()

    monkeypatch.setattr("adapters.secret_vault.httpx.AsyncClient", FakeClient)

    store = VaultSecretStore(vault_addr="https://vault", token="t", mount_point="secret", secret_base_path="openai")
    val = await store.get_secret("KEY")
    assert val == "s3cr3t"


@pytest.mark.asyncio
async def test_vault_secret_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None, timeout=None):
            class R404:
                status_code = 404

                def raise_for_status(self):
                    raise httpx.HTTPStatusError("not found", request=None, response=types.SimpleNamespace(status_code=404))

                def json(self):
                    return {}

            return R404()

    monkeypatch.setattr("adapters.secret_vault.httpx.AsyncClient", FakeClient)

    store = VaultSecretStore(vault_addr="https://vault", token="t", mount_point="secret", secret_base_path="openai")
    with pytest.raises(SecretNotFoundError):
        await store.get_secret("MISSING")
