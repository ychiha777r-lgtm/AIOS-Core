from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional

from core.ai_provider import AIProvider, ProviderResponse
from core.secret_store import SecretStore, SecretNotFoundError

# instrumented with tenacity and prometheus_client for retries and metrics
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception_type, stop_after_attempt, wait_exponential
from prometheus_client import Counter, Histogram


REQUESTS = Counter("provider_requests_total", "Total requests to provider", ["provider_id"]) 
FAILURES = Counter("provider_failures_total", "Total provider failures", ["provider_id", "reason"]) 
RETRIES = Counter("provider_retries_total", "Total provider retries", ["provider_id"]) 
LATENCY = Histogram("provider_latency_seconds", "Provider request latency seconds", ["provider_id"]) 


class OpenAIRateLimitError(RuntimeError):
    def __init__(self, retry_after: Optional[float] = None):
        super().__init__("rate limited")
        self.retry_after = retry_after


class OpenAIProvider(AIProvider):
    def __init__(
        self,
        secret_store: SecretStore,
        api_key_name: str = "OPENAI_API_KEY",
        model: str = "gpt-4",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
        retry_attempts: int = 3,
        retry_multiplier: float = 1.0,
    ) -> None:
        self.secret_store = secret_store
        self.api_key_name = api_key_name
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.provider_id = f"openai:{self.model}"
        self._api_key: Optional[str] = None
        self.retry_attempts = retry_attempts
        self.retry_multiplier = retry_multiplier

    async def start(self) -> None:
        try:
            self._api_key = await self.secret_store.get_secret(self.api_key_name)
        except SecretNotFoundError as exc:
            raise RuntimeError(f"OpenAI API key not found in SecretStore: {self.api_key_name}") from exc

    async def stop(self) -> None:
        self._api_key = None

    async def healthcheck(self, timeout: float | None = None) -> bool:
        return bool(self._api_key)

    async def _http_post(self, path: str, json_payload: Dict[str, Any], headers: Dict[str, str], timeout: Optional[float]) -> Dict[str, Any]:
        # prefer aiohttp, fallback to httpx; raise on non-2xx and on 429 raise rate limit error
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}{path}"
                async with session.post(url, json=json_payload, headers=headers, timeout=timeout) as resp:
                    text = await resp.text()
                    if resp.status == 429:
                        ra = resp.headers.get("Retry-After")
                        raise OpenAIRateLimitError(float(ra) if ra else None)
                    if resp.status >= 400:
                        raise RuntimeError(f"http error: {resp.status}\n{text}")
                    return json.loads(text)
        except OpenAIRateLimitError:
            raise
        except Exception:
            pass

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}{path}"
                r = await client.post(url, json=json_payload, headers=headers, timeout=timeout)
                if r.status_code == 429:
                    ra = r.headers.get("Retry-After")
                    raise OpenAIRateLimitError(float(ra) if ra else None)
                r.raise_for_status()
                return r.json()
        except OpenAIRateLimitError:
            raise
        except Exception as e:
            raise RuntimeError("Install aiohttp or httpx to use OpenAIProvider in runtime") from e

    async def request(self, prompt: str, **kwargs) -> ProviderResponse:
        if not self._api_key:
            raise RuntimeError("OpenAIProvider not started or API key missing")

        path = "/chat/completions"
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
        payload.update(kwargs.get("payload", {}))
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

        REQUESTS.labels(self.provider_id).inc()
        start = time.monotonic()

        async def _before_sleep(retry_state: RetryCallState) -> None:  # called before sleeping on retry
            RETRIES.labels(self.provider_id).inc()

        retrying = AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(self.retry_attempts),
            wait=wait_exponential(multiplier=self.retry_multiplier, min=1, max=10),
            retry=retry_if_exception_type((RuntimeError, OpenAIRateLimitError)),
            before_sleep=_before_sleep,
        )

        last_exc = None
        async for attempt in retrying:
            with attempt:
                try:
                    resp_json = await self._http_post(path, payload, headers, timeout=kwargs.get("timeout", self.timeout))
                    # parse
                    choice = resp_json.get("choices", [])[0]
                    if isinstance(choice, dict) and "message" in choice and "content" in choice["message"]:
                        text = choice["message"]["content"]
                    else:
                        text = choice.get("text", "") if isinstance(choice, dict) else json.dumps(resp_json)
                    LATENCY.labels(self.provider_id).observe(time.monotonic() - start)
                    return ProviderResponse(provider_id=self.provider_id, text=text, raw=resp_json)
                except OpenAIRateLimitError as e:
                    last_exc = e
                    # raise to trigger retry
                    raise
                except Exception as e:
                    last_exc = e
                    # raise to trigger retry
                    raise

        # exhausted
        FAILURES.labels(self.provider_id, type(last_exc).__name__ if last_exc is not None else "unknown").inc()
        raise last_exc or RuntimeError("all retries failed")
