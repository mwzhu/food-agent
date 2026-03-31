from __future__ import annotations

from typing import Any, Dict, List, Literal, Mapping

from shopper.memory.store import MemoryStore
from shopper.memory.types import AssembledContext, ContextBudget


NodeName = Literal["nutrition_planner", "meal_selector"]


class ContextAssembler:
    def __init__(self, memory_store: MemoryStore) -> None:
        self.memory_store = memory_store

    async def build_context(
        self,
        node_name: NodeName,
        state: Mapping[str, Any],
    ) -> AssembledContext:
        user_profile = state["user_profile"]

        if node_name == "nutrition_planner":
            payload = {
                "user_profile_summary": self._profile_summary(user_profile),
                "dietary_restrictions": user_profile["dietary_restrictions"],
                "allergies": user_profile["allergies"],
                "schedule": user_profile["schedule_json"],
            }
            memories = []
            token_budget = 1400
        elif node_name == "meal_selector":
            memories = await self.memory_store.recall(
                user_id=state["user_id"],
                query="meal planning preferences and prior feedback",
                top_k=5,
            )
            payload = {
                "user_profile_summary": self._profile_summary(user_profile),
                "nutrition_plan": state["nutrition_plan"],
                "schedule": user_profile["schedule_json"],
                "top_k_memories": [memory.content for memory in memories],
            }
            token_budget = 2200
        else:
            assert False, node_name

        budget = ContextBudget(
            token_budget=token_budget,
            tokens_used=self._estimate_tokens(payload),
            fields_included=list(payload.keys()),
            fields_dropped=[],
        )
        return AssembledContext(node_name=node_name, payload=payload, retrieved_memories=memories, budget=budget)

    def _profile_summary(self, user_profile: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "age": user_profile["age"],
            "sex": user_profile["sex"],
            "activity_level": user_profile["activity_level"],
            "goal": user_profile["goal"],
            "budget_weekly": user_profile["budget_weekly"],
            "household_size": user_profile["household_size"],
            "cooking_skill": user_profile["cooking_skill"],
        }

    def _estimate_tokens(self, payload: Mapping[str, Any]) -> int:
        rough_char_count = len(str(payload))
        assert rough_char_count > 0
        return rough_char_count // 4
