# Unit tests for ConnectionManager
import asyncio
import pytest
from unittest.mock import AsyncMock

from src.connection_manager import ConnectionManager
from src.rotation_config import RotationConfig

class DummyProvider:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.reload_called = 0

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def reload(self):
        self.reload_called += 1

@pytest.mark.asyncio
async def test_rotation_triggers_reload(tmp_path):
    provider = DummyProvider()
    # mock secret store with async get_secret
    seq = ["initial", "initial", "rotated"]
    async def get_secret(name):
        return seq.pop(0) if seq else "rotated"
    secret_store = AsyncMock()
    secret_store.get_secret.side_effect = get_secret

    config = RotationConfig(enabled=True, poll_interval=0.1, jitter=0)
    cm = ConnectionManager(provider, secret_store, config)

    await cm.start()
    # allow loop to run a bit
    await asyncio.sleep(0.35)
    await cm.stop()

    assert provider.reload_called >= 1
