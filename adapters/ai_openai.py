from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from core.ai_provider import AIProvider, ProviderResponse
from core.secret_store import SecretStore, SecretNotFoundError


class OpenAIProvider(AIProvider):
    """OpenAI provider adapter using either aiohttp or httpx (async).

    This adapter fetches the API key from a SecretStore at start(), and then
    issues requests to the OpenAI Chat Completions API. The implementation
    chooses an available HTTP client library (aiohttp preferred, httpx as
    fallback). For unit tests, the network method `_http_post` can be
    monkeypatched.
    """

    def __init__(
        self,
        secret_store: SecretStore,
        api_key_name: str = "OPENAI_API_KEY",
        model: str = "gpt-4",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
    ) -> None:
        self.secret_store = secret_store
        self.api_key_name = api_key_name
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.provider_id = f"openai:{self.model}"
        self._api_key: Optional[str] = None
        self._client = None

    async def start(self) -> None:
        try:
            self._api_key = await self.secret_store.get_secret(self.api_key_name)
        except SecretNotFoundError as exc:
            raise RuntimeError(f"OpenAI API key not found in SecretStore: {self.api_key_name}") from exc

    async def stop(self) -> None:
        # nothing to close for lightweight adapter; clients created per request
        self._api_key = None

    async def healthcheck(self, timeout: float | None = None) -> bool:
        # Basic health: we have a key loaded
        return bool(self._api_key)

    async def _http_post(self, path: str, json_payload: Dict[str, Any], headers: Dict[str, str], timeout: Optional[float]) -> Dict[str, Any]:
        """Perform HTTP POST to base_url+path and return parsed JSON.

        The implementation prefers aiohttp and falls back to httpx. For unit
        tests this method may be monkeypatched to return canned responses.
        """
        # prefer aiohttp
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}{path}"
                async with session.post(url, json=json_payload, headers=headers, timeout=timeout) as resp:
                    text = await resp.text()
                    return json.loads(text)
        except Exception:
            pass

        # fallback to httpx
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}{path}"
                r = await client.post(url, json=json_payload, headers=headers, timeout=timeout)
                return r.json()
        except Exception:
            raise RuntimeError("Install aiohttp or httpx to use OpenAIProvider in runtime")

    async def request(self, prompt: str, **kwargs) -> ProviderResponse:
        if not self._api_key:
            raise RuntimeError("OpenAIProvider not started or API key missing")

        # Build ChatCompletions payload by default; allow override via kwargs
        path = "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        # merge any provided fields
        payload.update(kwargs.get("payload", {}))

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        resp_json = await self._http_post(path, payload, headers, timeout=kwargs.get("timeout", self.timeout))

        # Attempt to parse typical Chat Completions response
        try:
            choice = resp_json["choices"][0]
            # support both message.content and text styles
            if "message" in choice and "content" in choice["message"]:
                text = choice["message"]["content"]
            else:
                text = choice.get("text", "")
        except Exception:
            # fallback: stringify
            text = json.dumps(resp_json)

        return ProviderResponse(provider_id=self.provider_id, text=text, raw=resp_json)
