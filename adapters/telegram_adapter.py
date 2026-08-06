import os
import asyncio
import httpx
from typing import Optional, Set

from core.service import BaseService
from core.provider_manager import ProviderManager


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USERS: Set[int] = set(
    int(x) for x in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",") if x.strip()
)
POLL_INTERVAL = float(os.getenv("TELEGRAM_POLL_INTERVAL", "1.0"))
MAX_RESPONSE_CHARS = int(os.getenv("TELEGRAM_MAX_RESPONSE_CHARS", "4000"))


class TelegramAdapter(BaseService):
    """Simple Telegram adapter service using long polling.

    Behaviour:
    - On start, spins a background task that long-polls getUpdates.
    - For each incoming text message, forwards the text to ProviderManager.request()
      and sends the provider response back to the chat.

    Notes:
    - TELEGRAM_TOKEN environment variable is required.
    - If TELEGRAM_ALLOWED_USERS is set (comma-separated user ids), only these users
      will be served.
    - This adapter deliberately keeps logic minimal so it can be adapted to
      project-specific message routing or richer chat state management.
    """

    def __init__(self, provider_manager: ProviderManager, *, name: str = "telegram-adapter"):
        # BaseService is a dataclass; call its initializer with name/version.
        super().__init__(name=name, version="0.1.0")
        self._pm = provider_manager
        self._task: Optional[asyncio.Task] = None
        self._offset: Optional[int] = None
        if not TELEGRAM_TOKEN:
            raise RuntimeError("TELEGRAM_TOKEN is required for TelegramAdapter")

    async def start(self) -> None:
        await super().start()
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await super().stop()

    async def _poll_loop(self) -> None:
        base = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                try:
                    params = {"timeout": 20}
                    if self._offset:
                        params["offset"] = self._offset
                    r = await client.get(f"{base}/getUpdates", params=params)
                    r.raise_for_status()
                    data = r.json()
                    if not data.get("ok"):
                        await asyncio.sleep(POLL_INTERVAL)
                        continue
                    for upd in data.get("result", []):
                        # advance offset to avoid reprocessing
                        self._offset = upd["update_id"] + 1
                        msg = upd.get("message") or upd.get("edited_message")
                        if not msg or "text" not in msg:
                            continue
                        from_id = msg["from"]["id"]
                        if ALLOWED_USERS and from_id not in ALLOWED_USERS:
                            # optionally: notify user they are not allowed
                            continue
                        text = msg["text"]

                        # call provider_manager to get AI response
                        try:
                            res = await self._pm.request(text, timeout=30.0)
                            # ProviderResponse shape may vary; prefer .text attribute
                            reply = getattr(res, "text", None) or getattr(res, "content", None) or str(res)
                        except Exception as e:
                            reply = f"Ошибка при получении ответа: {e}"

                        if len(reply) > MAX_RESPONSE_CHARS:
                            reply = reply[:MAX_RESPONSE_CHARS] + "\n\n...[truncated]"

                        try:
                            await client.post(
                                f"{base}/sendMessage",
                                json={
                                    "chat_id": msg["chat"]["id"],
                                    "text": reply,
                                    "reply_to_message_id": msg.get("message_id"),
                                },
                            )
                        except Exception:
                            # ignore send errors; continue polling
                            pass

                except asyncio.CancelledError:
                    break
                except Exception:
                    # simple backoff on unexpected errors
                    await asyncio.sleep(max(1.0, POLL_INTERVAL))
