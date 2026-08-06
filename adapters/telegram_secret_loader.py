from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Optional, Dict
import httpx
import getpass

from core.secret_store import SecretStore, SecretNotFoundError


class TokenMissingError(RuntimeError):
    pass


class TokenInvalidError(RuntimeError):
    pass


class SecretStoreUnavailableError(RuntimeError):
    pass


@dataclass
class TelegramSecretLoader:
    """Load TELEGRAM_TOKEN and TELEGRAM_ALLOWED_USERS from a secure source.

    Resolution order:
      1. SecretStore.get_secret("TELEGRAM_TOKEN") if available
      2. config/telegram_secret.env file (local, not committed)
      3. Interactive hidden prompt (getpass) — will save into SecretStore if provided

    The loader never prints or logs the token. It only returns success/failure
    and stores the token in the provided SecretStore.
    """

    config_path: str = "config/telegram_secret.env"
    http_timeout: float = 5.0

    async def _validate_token(self, token: str) -> bool:
        """Validate token by calling Telegram getMe. Do not log the token."""
        url = f"https://api.telegram.org/bot{token}/getMe"
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                r = await client.get(url)
                # do not include r.text in logs
                r.raise_for_status()
                data = r.json()
                return bool(data.get("ok"))
        except httpx.HTTPStatusError:
            return False
        except Exception:
            # treat networking issues as validation failure upstream
            return False

    def _read_config_file(self) -> Optional[Dict[str, str]]:
        if not os.path.exists(self.config_path):
            return None
        data: Dict[str, str] = {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    data[k.strip()] = v.strip()
            return data
        except Exception:
            return None

    async def _prompt_token(self) -> Optional[str]:
        # Use getpass in thread to avoid blocking the event loop
        def _get():
            try:
                return getpass.getpass("Enter TELEGRAM_TOKEN (hidden): ").strip()
            except Exception:
                return ""

        token = await asyncio.to_thread(_get)
        return token or None

    async def ensure_token(self, secret_store: Optional[SecretStore]) -> None:
        """Ensure TELEGRAM_TOKEN exists in the provided SecretStore.

        If SecretStore is None, attempt to read from config file or prompt the user
        and set the token only in the local environment (process env) for testing.
        """
        # 1) Try SecretStore
        token: Optional[str] = None
        if secret_store is not None:
            try:
                token = await secret_store.get_secret("TELEGRAM_TOKEN")
            except SecretNotFoundError:
                token = None
            except Exception as e:
                raise SecretStoreUnavailableError("SecretStore unavailable: %s" % e)

            if token:
                valid = await self._validate_token(token)
                if not valid:
                    raise TokenInvalidError("Token found in SecretStore is invalid")
                # token valid and in store; nothing else to do
                return

        # 2) Try config file
        cfg = self._read_config_file()
        if cfg:
            cfg_token = cfg.get("TELEGRAM_TOKEN")
            if cfg_token:
                valid = await self._validate_token(cfg_token)
                if valid:
                    # store into SecretStore if available, else into process env
                    if secret_store is not None:
                        await secret_store.set_secret("TELEGRAM_TOKEN", cfg_token)
                    else:
                        # store in process env for this run only
                        os.environ["TELEGRAM_TOKEN"] = cfg_token
                    # also optionally store allowed users
                    allowed = cfg.get("TELEGRAM_ALLOWED_USERS")
                    if allowed:
                        if secret_store is not None:
                            await secret_store.set_secret("TELEGRAM_ALLOWED_USERS", allowed)
                        else:
                            os.environ["TELEGRAM_ALLOWED_USERS"] = allowed
                    return
                else:
                    raise TokenInvalidError("Token found in config file is invalid")

        # 3) Interactive prompt
        token = await self._prompt_token()
        if not token:
            raise TokenMissingError("No token provided")

        valid = await self._validate_token(token)
        if not valid:
            raise TokenInvalidError("Provided token is invalid")

        # store token securely
        if secret_store is not None:
            await secret_store.set_secret("TELEGRAM_TOKEN", token)
            # prompt for allowed users but do not echo
            def _ask_allowed():
                try:
                    v = input("TELEGRAM_ALLOWED_USERS (comma separated, optional): ").strip()
                    return v
                except Exception:
                    return ""

            allowed = await asyncio.to_thread(_ask_allowed)
            if allowed:
                await secret_store.set_secret("TELEGRAM_ALLOWED_USERS", allowed)
        else:
            # no SecretStore: keep in env for process duration only
            os.environ["TELEGRAM_TOKEN"] = token


__all__ = ["TelegramSecretLoader", "TokenMissingError", "TokenInvalidError", "SecretStoreUnavailableError"]
