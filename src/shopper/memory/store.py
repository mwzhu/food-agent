from __future__ import annotations

from collections import defaultdict
from typing import DefaultDict

from shopper.memory.base import BaseMemoryStore
from shopper.schemas import MemoryEvent, PreferenceSummary


class InMemoryEpisodicMemoryStore(BaseMemoryStore):
    def __init__(self) -> None:
        self._events: DefaultDict[tuple[str, str], list[MemoryEvent]] = defaultdict(list)

    async def append(self, event: MemoryEvent) -> None:
        self._events[(event.user_id, event.namespace)].append(event)

    async def search(self, user_id: str, namespace: str, query: str, limit: int = 5) -> list[MemoryEvent]:
        events = self._events.get((user_id, namespace), [])
        scored: list[tuple[int, MemoryEvent]] = []
        terms = {token.lower() for token in query.split()}
        for event in events:
            haystack = f"{event.content} {event.metadata}".lower()
            score = sum(1 for term in terms if term in haystack)
            scored.append((score, event))
        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        return [event for _, event in scored[:limit]]

    async def distill(self, user_id: str) -> PreferenceSummary:
        likes: list[str] = []
        dislikes: list[str] = []
        notes: list[str] = []
        for (stored_user_id, namespace), events in self._events.items():
            if stored_user_id != user_id:
                continue
            for event in events[-10:]:
                lowered = event.content.lower()
                if namespace == "meal_feedback" and "love" in lowered:
                    likes.append(event.content)
                if "dislike" in lowered or "hate" in lowered:
                    dislikes.append(event.content)
                notes.append(event.content)
        return PreferenceSummary(likes=likes[:5], dislikes=dislikes[:5], notes=notes[:8])


class QdrantEpisodicMemoryStore(BaseMemoryStore):
    def __init__(self) -> None:
        self._message = (
            "Qdrant-backed episodic memory is not wired in this scaffold yet. "
            "Use InMemoryEpisodicMemoryStore for local development."
        )

    async def append(self, event: MemoryEvent) -> None:
        raise NotImplementedError(self._message)

    async def search(self, user_id: str, namespace: str, query: str, limit: int = 5) -> list[MemoryEvent]:
        raise NotImplementedError(self._message)

    async def distill(self, user_id: str) -> PreferenceSummary:
        raise NotImplementedError(self._message)

