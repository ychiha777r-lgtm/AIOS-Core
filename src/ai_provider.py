import asyncio
from abc import ABC, abstractmethod

class AIProvider(ABC):
    """
    Базовый интерфейс провайдера. Провайдеры должны реализовать
    start/stop и, опционально, более эффективный reload.
    """
    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    async def reload(self) -> None:
        """
        Дефолтная реализация reload: просто стоп + старт.
        Провайдеры могут переопределить для более мягкой смены ключей.
        """
        await self.stop()
        await self.start()
