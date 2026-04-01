from __future__ import annotations

from collections import defaultdict
from typing import Any, DefaultDict, Literal, Optional
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shopper.memory.types import EpisodicMemory
from shopper.models import EpisodicMemoryRecord
from shopper.schemas import PreferenceSummary


MemoryCategory = Literal[
    "meal_feedback",
    "store_behavior",
    "substitution_decisions",
    "general_preferences",
]
MemoryKey = tuple[str, MemoryCategory]
MEMORY_CATEGORIES: tuple[MemoryCategory, ...] = (
    "meal_feedback",
    "store_behavior",
    "substitution_decisions",
    "general_preferences",
)


class MemoryStore:
    def __init__(
        self,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self.session_factory = session_factory
        self._memories: DefaultDict[MemoryKey, list[EpisodicMemory]] = defaultdict(list)

    async def save_memory(
        self,
        user_id: str,
        category: MemoryCategory,
        content: str,
        metadata: dict[str, Any],
    ) -> str:
        assert category in MEMORY_CATEGORIES

        memory = EpisodicMemory(
            memory_id=str(uuid4()),
            user_id=user_id,
            category=category,
            content=content,
            metadata=dict(metadata),
        )
        self._memories[(user_id, category)].append(memory)
        if self.session_factory is not None:
            async with self.session_factory() as session:
                session.add(
                    EpisodicMemoryRecord(
                        memory_id=memory.memory_id,
                        user_id=user_id,
                        category=category,
                        content=content,
                        metadata_json=dict(metadata),
                    )
                )
                await session.commit()
        return memory.memory_id

    async def recall(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        categories: Optional[list[MemoryCategory]] = None,
    ) -> list[EpisodicMemory]:
        if self.session_factory is not None:
            await self._hydrate_user_memories(user_id, categories)

        query_terms = {token.lower() for token in query.split() if token}
        selected_categories = categories or sorted({
            category for stored_user_id, category in self._memories if stored_user_id == user_id
        })

        scored: list[tuple[int, EpisodicMemory]] = []
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
        if self.session_factory is not None:
            async with self.session_factory() as session:
                await session.execute(
                    delete(EpisodicMemoryRecord).where(
                        EpisodicMemoryRecord.user_id == user_id,
                        EpisodicMemoryRecord.memory_id == memory_id,
                    )
                )
                await session.commit()

    async def summarize_preferences(self, user_id: str) -> PreferenceSummary:
        if self.session_factory is not None:
            await self._hydrate_user_memories(user_id, None)

        memories = [
            memory
            for (stored_user_id, _category), category_memories in self._memories.items()
            if stored_user_id == user_id
            for memory in category_memories
        ]

        cuisines: dict[str, int] = defaultdict(int)
        avoided_ingredients: dict[str, int] = defaultdict(int)
        meal_types: dict[str, int] = defaultdict(int)
        notes: list[str] = []

        for memory in memories:
            cuisine = str(memory.metadata.get("cuisine", "")).strip().lower()
            ingredient = str(memory.metadata.get("avoided_ingredient", "")).strip().lower()
            meal_type = str(memory.metadata.get("meal_type", "")).strip().lower()
            if cuisine:
                cuisines[cuisine] += 1
            if ingredient:
                avoided_ingredients[ingredient] += 1
            if meal_type:
                meal_types[meal_type] += 1
            if memory.content and len(notes) < 3:
                notes.append(memory.content)

        return PreferenceSummary(
            preferred_cuisines=self._top_values(cuisines),
            avoided_ingredients=self._top_values(avoided_ingredients),
            preferred_meal_types=self._top_values(meal_types),
            notes=notes,
        )

    async def _hydrate_user_memories(
        self,
        user_id: str,
        categories: Optional[list[MemoryCategory]],
    ) -> None:
        assert self.session_factory is not None
        async with self.session_factory() as session:
            statement = select(EpisodicMemoryRecord).where(EpisodicMemoryRecord.user_id == user_id)
            if categories:
                statement = statement.where(EpisodicMemoryRecord.category.in_(categories))
            statement = statement.order_by(EpisodicMemoryRecord.created_at.desc())
            result = await session.execute(statement)
            records = result.scalars().all()

        if categories:
            target_categories = categories
        else:
            target_categories = list({record.category for record in records})

        for category in target_categories:
            self._memories[(user_id, category)] = []

        for record in records:
            self._memories[(record.user_id, record.category)].append(
                EpisodicMemory(
                    memory_id=record.memory_id,
                    user_id=record.user_id,
                    category=record.category,
                    content=record.content,
                    metadata=dict(record.metadata_json or {}),
                    created_at=record.created_at,
                )
            )

    def _top_values(self, counts: dict[str, int], limit: int = 3) -> list[str]:
        return [value for value, _count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]]
