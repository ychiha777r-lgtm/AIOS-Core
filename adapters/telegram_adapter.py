import os
import asyncio
import httpx
from typing import Optional, Set

from core.service import BaseService
from core.provider_manager import ProviderManager
from core.secret_store import SecretStore, SecretNotFoundError


# Environment-backed defaults; can be overridden by secret_store at start
TELEGRAM_TOKEN_ENV = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USERS_ENV = set(
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

    Token resolution order:
    1) Environment variable TELEGRAM_TOKEN
    2) SecretStore.get_secret("TELEGRAM_TOKEN") if a SecretStore instance is provided

    Notes:
    - TELEGRAM_ALLOWED_USERS may come from env (TELEGRAM_ALLOWED_USERS) or from
      secret store key TELEGRAM_ALLOWED_USERS (comma-separated user ids).
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
        *,
        name: str = "telegram-adapter",
        secret_store: Optional[SecretStore] = None,
    ):
        # BaseService is a dataclass; call its initializer with name/version.
        super().__init__(name=name, version="0.1.1")
        self._pm = provider_manager
        self._task: Optional[asyncio.Task] = None
        self._offset: Optional[int] = None
        self._secret_store = secret_store
        # runtime-populated fields
        self._token: Optional[str] = TELEGRAM_TOKEN_ENV
        self._allowed_users: Set[int] = set(ALLOWED_USERS_ENV)

    async def start(self) -> None:
        # Attempt to resolve token from secret store if not present in env
        if not self._token and self._secret_store:
            try:
                val = await self._secret_store.get_secret("TELEGRAM_TOKEN")
                if val:
                    self._token = val
            except SecretNotFoundError:
                # leave token None for later error
                pass

        # Resolve allowed users from secret store if env is empty
        if not self._allowed_users and self._secret_store:
            try:
                val = await self._secret_store.get_secret("TELEGRAM_ALLOWED_USERS")
                if val:
                    self._allowed_users = set(int(x) for x in val.split(",") if x.strip())
            except SecretNotFoundError:
                pass

        if not self._token:
            raise RuntimeError("TELEGRAM_TOKEN is required for TelegramAdapter (env or secret store)")

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
        base = f"https://api.telegram.org/bot{self._token}"
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
                        if self._allowed_users and from_id not in self._allowed_users:
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
