from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from langchain_core.messages import AIMessage

from shopper.agents.events import emit_run_event
from shopper.memory import ContextAssembler
from shopper.schemas.common import ContextMetadata
from shopper.schemas.user import UserProfileBase
from shopper.services import calculate_macros, calculate_tdee
from shopper.validators import validate_nutrition_plan


@dataclass
class NutritionPlannerNode:
    context_assembler: ContextAssembler

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_entered",
            phase="planning",
            node_name="nutrition_planner",
            message="Calculating nutrition targets from profile inputs.",
        )
        profile = UserProfileBase.model_validate(state["user_profile"])
        context = await self.context_assembler.build_context("nutrition_planner", state)

        tdee = calculate_tdee(profile)
        nutrition_plan = calculate_macros(tdee=tdee, goal=profile.goal, sex=profile.sex)
        nutrition_plan.applied_restrictions = sorted(set(profile.dietary_restrictions + profile.allergies))
        nutrition_plan.notes = self._build_notes(profile)
        assert not validate_nutrition_plan(nutrition_plan)
        metadata = ContextMetadata(
            node_name="nutrition_planner",
            tokens_used=context.budget.tokens_used,
            token_budget=context.budget.token_budget,
            fields_included=context.budget.fields_included,
            fields_dropped=context.budget.fields_dropped,
            retrieved_memory_ids=[memory.memory_id for memory in context.retrieved_memories],
        )

        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_completed",
            phase="planning",
            node_name="nutrition_planner",
            message="Calculated a {calories}-calorie daily target.".format(
                calories=nutrition_plan.daily_calories
            ),
            data={"daily_calories": nutrition_plan.daily_calories, "tdee": nutrition_plan.tdee},
        )

        return {
            "nutrition_plan": nutrition_plan.model_dump(mode="json"),
            "context_metadata": [metadata.model_dump(mode="json")],
            "messages": [
                AIMessage(
                    content=(
                        "Nutrition plan created with TDEE {tdee}."
                    ).format(tdee=nutrition_plan.tdee)
                )
            ],
        }

    def _build_notes(self, profile: UserProfileBase) -> str:
        note_parts = [
            "Goal-aligned macro targets based on Mifflin-St Jeor maintenance calories.",
            "Cooking skill: {skill}.".format(skill=profile.cooking_skill),
        ]
        if profile.dietary_restrictions:
            note_parts.append(
                "Respect dietary restrictions: {restrictions}.".format(
                    restrictions=", ".join(profile.dietary_restrictions)
                )
            )
        if profile.allergies:
            note_parts.append("Hard-exclude allergens: {allergies}.".format(allergies=", ".join(profile.allergies)))
        if profile.schedule_json:
            note_parts.append("Weekly schedule was considered for meal cadence.")
        return " ".join(note_parts)
