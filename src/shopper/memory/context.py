from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shopper.schemas import BasketPlan, MealPlan, NutritionTargets, ProfileFacts


@dataclass
class ContextBundle:
    payload: dict[str, Any]
    included_keys: list[str]
    dropped_keys: list[str]
    token_budget: int


class ContextAssembler:
    def __init__(self, default_token_budget: int = 1200) -> None:
        self.default_token_budget = default_token_budget

    def build_planning_context(
        self,
        *,
        profile: ProfileFacts,
        nutrition_targets: NutritionTargets,
        schedule_summary: str,
        pantry_snapshot: list[dict[str, Any]],
        relevant_memories: list[str],
        candidate_recipe_names: list[str],
    ) -> ContextBundle:
        payload = {
            "profile_summary": profile.model_dump(),
            "nutrition_targets": nutrition_targets.model_dump(),
            "schedule_summary": schedule_summary,
            "pantry_snapshot": pantry_snapshot[:12],
            "relevant_memories": relevant_memories[:5],
            "candidate_recipe_names": candidate_recipe_names[:8],
        }
        return ContextBundle(
            payload=payload,
            included_keys=list(payload.keys()),
            dropped_keys=[],
            token_budget=self.default_token_budget,
        )

    def build_shopping_context(
        self,
        *,
        meal_plan: MealPlan,
        grocery_demand: list[dict[str, Any]],
        budget_weekly: float,
        preferred_stores: list[str],
        relevant_memories: list[str],
    ) -> ContextBundle:
        payload = {
            "meal_plan": meal_plan.model_dump(),
            "grocery_demand": grocery_demand[:20],
            "budget_weekly": budget_weekly,
            "preferred_stores": preferred_stores,
            "relevant_memories": relevant_memories[:5],
        }
        return ContextBundle(
            payload=payload,
            included_keys=list(payload.keys()),
            dropped_keys=[],
            token_budget=self.default_token_budget,
        )

    def build_execution_context(
        self,
        *,
        basket_plan: BasketPlan,
        approval_required: bool,
        recent_browser_state: dict[str, Any],
    ) -> ContextBundle:
        payload = {
            "basket_plan": basket_plan.model_dump(),
            "approval_required": approval_required,
            "recent_browser_state": recent_browser_state,
        }
        return ContextBundle(
            payload=payload,
            included_keys=list(payload.keys()),
            dropped_keys=[],
            token_budget=self.default_token_budget,
        )

