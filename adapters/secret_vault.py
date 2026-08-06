from __future__ import annotations

import asyncio
from typing import Iterable, Optional

try:
    import hvac
except Exception:  # pragma: no cover - hvac may not be installed in test env
    hvac = None

import httpx

from core.secret_store import SecretNotFoundError, SecretStore


class VaultError(RuntimeError):
    pass


class VaultSecretStore(SecretStore):
    """SecretStore implementation backed by HashiCorp Vault.

    This adapter supports KV v2 secrets engine by default. It will try to use
    the hvac client if available; otherwise it falls back to the HTTP API via
    httpx.

    Configuration (via env or kwargs):
    - vault_addr: base URL for Vault (e.g., https://vault.example.com)
    - token: Vault token with permission to read secrets
    - mount_point: KV mount path (default: secret)
    - secret_base_path: base path under the mount where secrets live (default: "openai")

    Example secret path read: GET /v1/{mount_point}/data/{secret_base_path}/{name}
    """

    def __init__(
        self,
        vault_addr: str,
        token: str,
        mount_point: str = "secret",
        secret_base_path: str = "openai",
    ) -> None:
        self.vault_addr = vault_addr.rstrip("/")
        self.token = token
        self.mount_point = mount_point.strip("/")
        self.secret_base_path = secret_base_path.strip("/")
        self._client = None
        if hvac is not None:
            # hvac client is synchronous; we'll call it via to_thread
            self._client = hvac.Client(url=self.vault_addr, token=self.token)

    async def _http_get(self, path: str) -> dict:
        url = f"{self.vault_addr}{path}"
        headers = {"X-Vault-Token": self.token}
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=headers, timeout=10.0)
            r.raise_for_status()
            return r.json()

    async def get_secret(self, name: str) -> str:
        path = f"/v1/{self.mount_point}/data/{self.secret_base_path}/{name}"
        if self._client is not None:
            # use hvac synchronously in thread
            def _read():
                try:
                    return self._client.secrets.kv.v2.read_secret_version(path=f"{self.secret_base_path}/{name}")
                except Exception as e:
                    raise VaultError(str(e)) from e

            data = await asyncio.to_thread(_read)
            # hvac returns data['data']['data'] structure for KV v2
            try:
                return data["data"]["data"]["value"]
            except Exception as e:  # pragma: no cover - defensive
                raise SecretNotFoundError(name) from e
        else:
            # fall back to httpx
            try:
                data = await self._http_get(path)
                return data["data"]["data"]["value"]
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise SecretNotFoundError(name) from e
                raise VaultError(str(e)) from e

    async def set_secret(self, name: str, value: str) -> None:
        # write secret (KV v2): POST /v1/{mount_point}/data/{path}
        path = f"/v1/{self.mount_point}/data/{self.secret_base_path}/{name}"
        payload = {"data": {"value": value}}
        if self._client is not None:
            def _write():
                try:
                    return self._client.secrets.kv.v2.create_or_update_secret(path=f"{self.secret_base_path}/{name}", secret={"value": value})
                except Exception as e:
                    raise VaultError(str(e)) from e

            await asyncio.to_thread(_write)
            return
        async with httpx.AsyncClient() as client:
            url = f"{self.vault_addr}{path}"
            headers = {"X-Vault-Token": self.token}
            r = await client.post(url, json=payload, headers=headers, timeout=10.0)
            r.raise_for_status()

    async def list_secrets(self) -> Iterable[str]:
        # List secrets under base path: LIST /v1/{mount_point}/metadata/{secret_base_path}
        path = f"/v1/{self.mount_point}/metadata/{self.secret_base_path}"
        if self._client is not None:
            def _list():
                try:
                    return self._client.secrets.kv.v2.list_secrets(path=self.secret_base_path)
                except Exception as e:
                    raise VaultError(str(e)) from e

            data = await asyncio.to_thread(_list)
            try:
                return data.get("data", {}).get("keys", [])
            except Exception:
                return []
        else:
            try:
                url = f"/v1/{self.mount_point}/metadata/{self.secret_base_path}"
                data = await self._http_get(url)
                return data.get("data", {}).get("keys", [])
            except httpx.HTTPStatusError:
                return []

    async def rotate_secret(self, name: str, new_value: str) -> None:
        # rotate is alias to set_secret for KV v2
        await self.set_secret(name, new_value)
