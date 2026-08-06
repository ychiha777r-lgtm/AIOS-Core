import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

import aiohttp

from core.service import BaseService, ServiceStatus, Health
from core.secret_store import SecretStore, SecretNotFoundError

logger = logging.getLogger(__name__)

# Type of async callable that turns user text -> reply text
AIRequestCallable = Callable[[str], Awaitable[str]]


class TelegramService(BaseService):
    """
    Simple Telegram bot service that:
    - reads TELEGRAM_BOT_TOKEN from SecretStore
    - long-polls getUpdates
    - on text message calls provided ai_request(text) -> reply_text
    - sends reply with sendMessage
    """

    def __init__(
        self,
        secret_store: SecretStore,
        ai_request: AIRequestCallable,
        token_secret_name: str = "TELEGRAM_BOT_TOKEN",
        poll_timeout: int = 30,
        name: str = "telegram-bot",
        version: str = "0.1.0",
    ) -> None:
        super().__init__(name=name, version=version)
        self.secret_store = secret_store
        self.ai_request = ai_request
        self.token_secret_name = token_secret_name
        self.poll_timeout = poll_timeout
        self._task: Optional[asyncio.Task] = None
        self._stopping = asyncio.Event()
        self._last_update_id: Optional[int] = None
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        if self.status is ServiceStatus.RUNNING:
            return
        await super().start()
        try:
            token = await self.secret_store.get_secret(self.token_secret_name)
        except SecretNotFoundError:
            self.status = ServiceStatus.FAILED
            raise RuntimeError(f"Telegram token not found in SecretStore: {self.token_secret_name}")

        self._session = aiohttp.ClientSession()
        self._stopping.clear()
        self._task = asyncio.create_task(self._poll_loop(token))
        self.status = ServiceStatus.RUNNING
        logger.info("TelegramService started")

    async def stop(self) -> None:
        if self.status is ServiceStatus.STOPPED:
            return
        self._stopping.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._session:
            await self._session.close()
            self._session = None
        await super().stop()
        logger.info("TelegramService stopped")

    async def restart(self) -> None:
        await super().restart()

    async def health(self) -> Health:
        status = ServiceStatus.RUNNING if self.status is ServiceStatus.RUNNING else ServiceStatus.DEGRADED
        details = {"polling": self._task is not None and not self._task.done()}
        return Health(status=status, details=details)

    async def _poll_loop(self, token: str) -> None:
        api = f"https://api.telegram.org/bot{token}"
        assert self._session is not None

        while not self._stopping.is_set():
            try:
                params = {"timeout": self.poll_timeout, "allowed_updates": ["message"]}
                if self._last_update_id is not None:
                    params["offset"] = self._last_update_id + 1
                url = f"{api}/getUpdates"
                async with self._session.get(url, params=params, timeout=self.poll_timeout + 10) as resp:
                    data = await resp.json()
                if not data.get("ok"):
                    logger.warning("getUpdates not ok: %s", data)
                    await asyncio.sleep(1)
                    continue
                updates = data.get("result", [])
                for u in updates:
                    # update last_update_id
                    self._last_update_id = u["update_id"]
                    # handle message
                    msg = u.get("message") or u.get("edited_message")
                    if not msg:
                        continue
                    chat = msg.get("chat", {})
                    chat_id = chat.get("id")
                    text = msg.get("text")
                    if not text or chat_id is None:
                        # ignore non-text messages for now
                        continue
                    # call AI
                    try:
                        reply = await self.ai_request(text)
                    except Exception as e:
                        logger.exception("AI request failed: %s", e)
                        reply = "Извините, при обработке запроса произошла ошибка."
                    # send reply
                    await self._send_message(api, chat_id, reply)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in Telegram polling loop")
                # backoff on error
                await asyncio.sleep(2)

    async def _send_message(self, api_base: str, chat_id: int, text: str) -> None:
        assert self._session is not None
        url = f"{api_base}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}
        try:
            async with self._session.post(url, json=payload, timeout=10) as resp:
                # best-effort logging
                _ = await resp.json()
        except Exception:
            logger.exception("Failed to send message to %s", chat_id)
