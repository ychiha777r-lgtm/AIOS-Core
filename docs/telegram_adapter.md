# Telegram adapter for AIOS-Core

This document describes the minimal Telegram adapter added in feature/telegram-adapter.

What was added
- adapters/telegram_adapter.py — an async BaseService that long-polls Telegram
  for updates, forwards incoming text messages to ProviderManager.request(), and
  sends back the provider response.

Environment variables
- TELEGRAM_TOKEN (required) — Bot token from BotFather.
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

2. Set environment variables (example):
   ```bash
   export TELEGRAM_TOKEN="123456:ABC-DEF..."
   export TELEGRAM_ALLOWED_USERS="123456789,987654321"
   ```

3. Instantiate and start the adapter from your service entrypoint. Minimal example:

```python
import asyncio
from core.provider_manager import ProviderManager
from adapters.telegram_adapter import TelegramAdapter

async def main():
    pm = ProviderManager()
    # register your AI providers with pm here...

    tg = TelegramAdapter(pm)
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
- This is a minimal, opinionated adapter intended to be a starting point. You may want to:
  - Integrate adapter lifecycle into an existing service manager in the project.
  - Add message routing / session management for multi-step conversations.
  - Replace polling with webhooks if you have a public HTTPS endpoint.

Security
- Keep TELEGRAM_TOKEN secret; do not commit it to the repo.
- Use TELEGRAM_ALLOWED_USERS to restrict who can trigger the bot actions.
