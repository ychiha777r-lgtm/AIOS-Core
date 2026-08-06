from __future__ import annotations

import abc
from typing import Dict, Iterable, Optional


class SecretNotFoundError(RuntimeError):
    pass


class SecretStore(abc.ABC):
    """Abstract secret store.

    Implementations must avoid logging secrets and should support async interfaces
    if they perform I/O. For simplicity many adapters here are synchronous but
    expose async methods for compatibility.
    """

    @abc.abstractmethod
    async def get_secret(self, name: str) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    async def set_secret(self, name: str, value: str) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_secrets(self) -> Iterable[str]:
        raise NotImplementedError

    @abc.abstractmethod
    async def rotate_secret(self, name: str, new_value: str) -> None:
        raise NotImplementedError
