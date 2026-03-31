from __future__ import annotations

from abc import ABC, abstractmethod

from shopper.schemas import MemoryEvent, PreferenceSummary


class BaseMemoryStore(ABC):
    @abstractmethod
    async def append(self, event: MemoryEvent) -> None:
        raise NotImplementedError

    @abstractmethod
    async def search(self, user_id: str, namespace: str, query: str, limit: int = 5) -> list[MemoryEvent]:
        raise NotImplementedError

    @abstractmethod
    async def distill(self, user_id: str) -> PreferenceSummary:
        raise NotImplementedError

