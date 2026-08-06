"""Run AIOS Core with TelegramAdapter registered via ConnectionManager.

This script loads Telegram secrets via TelegramSecretLoader and uses the
ConnectionManager to start ProviderManager and registered adapters.

It prints only high-level statuses and does not expose the token.
"""
from __future__ import annotations

import asyncio
import os
import sys
import traceback

from core.provider_manager import ProviderManager
from adapters.ai_mock import MockProvider, MockProviderConfig
from adapters.telegram_adapter import TelegramAdapter
from adapters.secret_env import EnvSecretStore
from adapters.secret_vault import VaultSecretStore
from adapters.telegram_secret_loader import (
    TelegramSecretLoader,
    TokenMissingError,
    TokenInvalidError,
    SecretStoreUnavailableError,
)
from core.connection_manager import ConnectionManager


async def main():
    # Choose SecretStore: Vault if configured, otherwise EnvSecretStore
    secret_store = None
    try:
        vault_addr = os.environ.get("VAULT_ADDR")
        vault_token = os.environ.get("VAULT_TOKEN")
        if vault_addr and vault_token:
            secret_store = VaultSecretStore(vault_addr=vault_addr, token=vault_token, mount_point=os.environ.get("VAULT_MOUNT", "secret"), secret_base_path=os.environ.get("VAOS_SECRET_BASE", "aios"))
        else:
            secret_store = EnvSecretStore()
    except Exception as e:
        print("Error initializing SecretStore: %s" % e, file=sys.stderr)
        return 1

    loader = TelegramSecretLoader()
    try:
        await loader.ensure_token(secret_store)
    except TokenMissingError:
        print("Error: TELEGRAM_TOKEN not provided. Aborting.")
        return 2
    except TokenInvalidError:
        print("Error: TELEGRAM_TOKEN appears invalid. Please verify the token and try again.")
        return 3
    except SecretStoreUnavailableError as e:
        print("Error: SecretStore unavailable: %s" % e, file=sys.stderr)
        return 4
    except Exception as e:
        print("Unexpected error while loading token:", file=sys.stderr)
        traceback.print_exc()
        return 10

    # Build provider manager and register providers
    pm = ProviderManager()
    mock_cfg = MockProviderConfig(provider_id="mock-1", response_text="Привет от AI!")
    mock = MockProvider(mock_cfg)
    pm.register(mock)

    # Create ConnectionManager and register TelegramAdapter
    cm = ConnectionManager(secret_store=secret_store, provider_manager=pm)
    tg = TelegramAdapter(pm, secret_store=secret_store)
    cm.register_service(tg)

    # Start the system
    try:
        await cm.start()
    except Exception as e:
        print("Error starting AIOS Core / TelegramAdapter: %s" % e, file=sys.stderr)
        # attempt graceful shutdown
        try:
            await cm.stop()
        except Exception:
            pass
        return 5

    # If we reached here, both started
    print("Telegram connected")
    print("AIOS Core running")

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            await cm.stop()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
