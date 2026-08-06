from __future__ import annotations

import os
from typing import Iterable

from core.secret_store import SecretStore, SecretNotFoundError


class EnvSecretStore(SecretStore):
    """Simple SecretStore backed by environment variables.

    Note: This is intended for local development and CI where secrets are
    injected into the environment. It is NOT suitable for production secret
    management but is convenient for tests.
    """

    async def get_secret(self, name: str) -> str:
        key = name
        value = os.environ.get(key)
        if value is None:
            raise SecretNotFoundError(name)
        return value

    async def set_secret(self, name: str, value: str) -> None:
        # This writes to the current process environment for testability.
        os.environ[name] = value

    async def list_secrets(self) -> Iterable[str]:
        # Only return keys that look like secrets (convention)
        for k in os.environ.keys():
            if k.startswith("SECRET_") or k.startswith("API_"):
                yield k

    async def rotate_secret(self, name: str, new_value: str) -> None:
        # rotate by overwriting in environment
        await self.set_secret(name, new_value)
