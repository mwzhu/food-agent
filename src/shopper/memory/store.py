from __future__ import annotations

from collections import defaultdict
from typing import DefaultDict, Dict, List, Tuple
from uuid import uuid4

from shopper.memory.types import EpisodicMemory


class MemoryStore:
    def __init__(self) -> None:
        self._memories: DefaultDict[Tuple[str, str], List[EpisodicMemory]] = defaultdict(list)

    async def save_memory(self, user_id: str, category: str, content: str, metadata: Dict) -> str:
        memory = EpisodicMemory(
            memory_id=str(uuid4()),
            user_id=user_id,
            category=category,
            content=content,
            metadata=dict(metadata),
        )
        self._memories[(user_id, category)].append(memory)
        return memory.memory_id

    async def recall(self, user_id: str, query: str, top_k: int = 5) -> List[EpisodicMemory]:
        query_terms = {token.lower() for token in query.split() if token}
        selected_categories = sorted({category for stored_user_id, category in self._memories if stored_user_id == user_id})

        scored: List[Tuple[int, EpisodicMemory]] = []
        for category in selected_categories:
            for memory in self._memories.get((user_id, category), []):
                haystack = "{content} {metadata}".format(
                    content=memory.content.lower(),
                    metadata=str(memory.metadata).lower(),
                )
                score = sum(1 for term in query_terms if term in haystack)
                if score or not query_terms:
                    scored.append((score, memory))

        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        return [memory for _, memory in scored[:top_k]]

    async def forget(self, user_id: str, memory_id: str) -> None:
        for key, memories in list(self._memories.items()):
            if key[0] != user_id:
                continue
            self._memories[key] = [memory for memory in memories if memory.memory_id != memory_id]
