import asyncio
import logging
import random
import time
from typing import Optional

from prometheus_client import Counter, Gauge, Histogram

from src.rotation_config import RotationConfig
from src.ai_provider import AIProvider

log = logging.getLogger(__name__)

# Prometheus metrics
_secret_rotations_total = Counter("secret_rotations_total", "Total successful secret rotations")
_secret_rotation_failures_total = Counter("secret_rotation_failures_total", "Total failed secret rotations")
_secret_rotation_duration_seconds = Histogram("secret_rotation_duration_seconds", "Duration of secret rotation attempts")
_last_secret_rotation_timestamp = Gauge("last_secret_rotation_timestamp", "Timestamp of last successful secret rotation")

class ConnectionManager:
    def __init__(self, provider: AIProvider, secret_store, config: RotationConfig):
        """
        secret_store: объект с async методом get_secret(name) -> Optional[str]
        provider: AIProvider (OpenAIProvider и т.д.)
        """
        self.provider = provider
        self.secret_store = secret_store
        self.config = config
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._stopped = asyncio.Event()
        self._current_secret: Optional[str] = None

    async def start(self):
        log.info("ConnectionManager starting")
        # Попробуем сразу получить текущий секрет и запустить провайдера
        try:
            initial = await self._read_secret()
            if initial is not None:
                self._current_secret = initial
            await self.provider.start()
        except Exception:
            log.exception("Failed to start provider on startup; provider will be attempted again by rotation loop")

        self._stopped.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        log.info("ConnectionManager stopping")
        self._stopped.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        try:
            await self.provider.stop()
        except Exception:
            log.exception("Error stopping provider")

    async def _read_secret(self) -> Optional[str]:
        """
        Асинхронно читает секрет из SecretStore.
        Предполагается, что secret_store имеет метод async get_secret(name) -> Optional[str]
        """
        try:
            return await self.secret_store.get_secret(self.config.secret_name)
        except Exception:
            log.exception("Failed to read secret from SecretStore")
            return None

    async def _run_loop(self):
        log.info("ConnectionManager rotation loop started (poll_interval=%s)", self.config.poll_interval)
        while not self._stopped.is_set() and self.config.enabled:
            jitter = random.uniform(-self.config.jitter, self.config.jitter) if self.config.jitter else 0
            wait_time = max(0.1, self.config.poll_interval + jitter)
            try:
                await asyncio.sleep(wait_time)
                new_value = await self._read_secret()
                if new_value is None:
                    continue
                if self._current_secret == new_value:
                    # ничего не меняется
                    continue
                # обнаружено изменение
                async with self._lock:
                    # Повторная проверка после получения локального lock-а
                    if self._current_secret == new_value:
                        continue
                    start_ts = time.time()
                    try:
                        with _secret_rotation_duration_seconds.time():
                            log.info("Secret %s changed — attempting rotation", self.config.secret_name)
                            # если провайдер реализует reload — вызовём; иначе stop/start
                            try:
                                await asyncio.wait_for(self.provider.reload(), timeout=self.config.reload_timeout)
                            except asyncio.TimeoutError:
                                raise RuntimeError("Provider reload timed out")
                            except AttributeError:
                                # на всякий случай: если provider не имеет reload
                                await asyncio.wait_for(self.provider.stop(), timeout=self.config.reload_timeout)
                                await asyncio.wait_for(self.provider.start(), timeout=self.config.reload_timeout)
                        # успех
                        _secret_rotations_total.inc()
                        _last_secret_rotation_timestamp.set_to_current_time()
                        self._current_secret = new_value
                        log.info("Provider reloaded successfully after secret rotation")
                    except Exception:
                        _secret_rotation_failures_total.inc()
                        log.exception("Secret rotation failed; leaving old secret active")
                    finally:
                        duration = time.time() - start_ts
                        log.debug("Rotation attempt duration: %.3fs", duration)
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Unexpected error in rotation loop; will continue")
        log.info("Rotation loop ended")
