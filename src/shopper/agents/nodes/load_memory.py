from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from langchain_core.messages import AIMessage

from shopper.agents.events import emit_run_event
from shopper.memory import ContextAssembler, MemoryStore
from shopper.schemas import ContextMetadata
from shopper.schemas.user import UserProfileBase


@dataclass
class LoadMemoryNode:
    context_assembler: ContextAssembler
    memory_store: MemoryStore

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_entered",
            phase="memory",
            node_name="load_memory",
            message="Loading learned preferences and relevant prior memories.",
        )

        profile = UserProfileBase.model_validate(state["user_profile"])
        context = await self.context_assembler.build_context("load_memory", state)
        memories = await self.memory_store.recall(
            user_id=state["user_id"],
            query=self._build_query(profile),
            top_k=6,
            categories=["meal_feedback", "substitution_decisions", "general_preferences"],
        )
        preference_summary = await self.memory_store.summarize_preferences(state["user_id"])
        metadata = ContextMetadata(
            node_name="load_memory",
            tokens_used=context.budget.tokens_used,
            token_budget=context.budget.token_budget,
            fields_included=context.budget.fields_included,
            fields_dropped=context.budget.fields_dropped,
            retrieved_memory_ids=[memory.memory_id for memory in memories],
        )

        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_completed",
            phase="memory",
            node_name="load_memory",
            message="Loaded {count} relevant memories.".format(count=len(memories)),
            data={"memory_count": len(memories)},
        )

        return {
            "user_preferences_learned": preference_summary.model_dump(mode="json"),
            "retrieved_memories": [memory.model_dump(mode="json") for memory in memories],
            "context_metadata": [metadata.model_dump(mode="json")],
            "messages": [AIMessage(content="Memory context assembled for this run.")],
        }

    def _build_query(self, user_profile: UserProfileBase) -> str:
        parts = [
            user_profile.goal,
            "meal planning preferences",
            " ".join(user_profile.dietary_restrictions),
            " ".join(user_profile.allergies),
        ]
        return " ".join(part for part in parts if part).strip()
