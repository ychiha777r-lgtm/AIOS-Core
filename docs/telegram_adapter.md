# Telegram adapter for AIOS-Core

This document describes the Telegram adapter added in feature/telegram-adapter.

What was added
- adapters/telegram_adapter.py — an async BaseService that long-polls Telegram
  for updates, forwards incoming text messages to ProviderManager.request(), and
  sends back the provider response.

Token resolution
- The adapter now supports resolving the telegram token and optional allowed users
  from either environment variables or the project's SecretStore implementation.

Resolution order for TELEGRAM_TOKEN:
1) Environment variable TELEGRAM_TOKEN
2) SecretStore.get_secret("TELEGRAM_TOKEN") if a SecretStore instance is provided

Resolution order for TELEGRAM_ALLOWED_USERS:
1) Environment variable TELEGRAM_ALLOWED_USERS (comma-separated user ids)
2) SecretStore.get_secret("TELEGRAM_ALLOWED_USERS") if present

Environment variables
- TELEGRAM_TOKEN (may be provided via env or secret store) — Bot token from BotFather.
- TELEGRAM_ALLOWED_USERS (optional) — comma-separated Telegram user IDs allowed to use the bot. If empty, the bot will accept messages from any user.
- TELEGRAM_POLL_INTERVAL (optional) — polling loop delay in seconds (default 1.0).
- TELEGRAM_MAX_RESPONSE_CHARS (optional) — maximum characters to send in reply (default 4000).

How to use
1. Install dependencies (httpx is already in requirements.txt):
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Provide token via SecretStore or env:
   - Using environment variable (quick test):
     ```bash
     export TELEGRAM_TOKEN="123456:ABC-DEF..."
     ```
   - Using SecretStore implementation: store TELEGRAM_TOKEN in your secret store under the key TELEGRAM_TOKEN and pass the SecretStore instance to TelegramAdapter().

3. Instantiate and start the adapter from your service entrypoint. Minimal example:

```python
import asyncio
from core.provider_manager import ProviderManager
from adapters.telegram_adapter import TelegramAdapter
from core.secret_store import SecretStore

async def main():
    pm = ProviderManager()
    # register your AI providers with pm here...

    # If you have a SecretStore implementation, create it and pass here:
    # secret_store = MySecretStore(...)
    secret_store = None

    tg = TelegramAdapter(pm, secret_store=secret_store)
    await tg.start()
    try:
        # keep running until cancelled
        await asyncio.Event().wait()
    finally:
        await tg.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

Notes & next steps
- This adapter is minimal. Consider:
  - Integrating adapter lifecycle into an existing ConnectionManager.
  - Adding message routing, session management for multi-step flows.
  - Replacing polling with webhooks if you have a public HTTPS endpoint.

Security
- Keep TELEGRAM_TOKEN secret; do not commit it to the repo.
- Use TELEGRAM_ALLOWED_USERS to restrict who can trigger bot actions.
