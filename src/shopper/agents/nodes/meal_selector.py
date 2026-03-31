from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from langchain_core.messages import AIMessage

from shopper.memory import ContextAssembler
from shopper.schemas.common import ContextMetadata, MealSlot, NutritionPlan
from shopper.schemas.user import UserProfileBase


PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "meal_selector.md"
DAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

MEAL_LIBRARY = {
    "breakfast": [
        {"recipe_name": "Protein Overnight Oats", "prep_time_min": 10, "tags": ["vegetarian"]},
        {"recipe_name": "Greek Yogurt Berry Bowl", "prep_time_min": 5, "tags": ["vegetarian"]},
        {"recipe_name": "Egg and Avocado Toast", "prep_time_min": 12, "tags": []},
    ],
    "lunch": [
        {"recipe_name": "Chicken Quinoa Prep Bowl", "prep_time_min": 15, "tags": []},
        {"recipe_name": "Lentil Power Salad", "prep_time_min": 15, "tags": ["vegetarian", "vegan"]},
        {"recipe_name": "Turkey Hummus Wrap", "prep_time_min": 10, "tags": []},
    ],
    "dinner": [
        {"recipe_name": "Sheet Pan Herb Chicken", "prep_time_min": 30, "tags": []},
        {"recipe_name": "Tofu Vegetable Stir Fry", "prep_time_min": 25, "tags": ["vegetarian", "vegan"]},
        {"recipe_name": "Salmon Rice Bowl", "prep_time_min": 25, "tags": []},
    ],
}

CALORIE_SPLITS = {
    "breakfast": 0.25,
    "lunch": 0.35,
    "dinner": 0.40,
}


@dataclass
class MealSelectorNode:
    context_assembler: ContextAssembler

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        profile = UserProfileBase.model_validate(state["user_profile"])
        nutrition_plan = NutritionPlan.model_validate(state["nutrition_plan"])
        prompt_template = PROMPT_PATH.read_text(encoding="utf-8").strip()
        assert prompt_template
        context = await self.context_assembler.build_context("meal_selector", state)
        selected_meals = self._build_stub_plan(profile, nutrition_plan)
        metadata = ContextMetadata(
            node_name="meal_selector",
            tokens_used=context.budget.tokens_used,
            token_budget=context.budget.token_budget,
            fields_included=context.budget.fields_included,
            fields_dropped=context.budget.fields_dropped,
            retrieved_memory_ids=[memory.memory_id for memory in context.retrieved_memories],
        )

        return {
            "selected_meals": [meal.model_dump() for meal in selected_meals],
            "context_metadata": [metadata.model_dump()],
            "messages": [
                AIMessage(
                    content=(
                        "Built a 7 day meal plan from prompt template {template}: {summary}"
                    ).format(
                        template=PROMPT_PATH.name,
                        summary=prompt_template.splitlines()[0],
                    )
                )
            ],
        }

    def _build_stub_plan(self, profile: UserProfileBase, nutrition_plan: NutritionPlan) -> List[MealSlot]:
        plan: List[MealSlot] = []
        restrictions = {item.lower() for item in profile.dietary_restrictions}
        allergies = {item.lower() for item in profile.allergies}

        for day_index, day in enumerate(DAYS):
            for meal_type in ("breakfast", "lunch", "dinner"):
                template = self._pick_template(meal_type, day_index, restrictions, allergies)
                calories = int(round(nutrition_plan.daily_calories * CALORIE_SPLITS[meal_type]))
                plan.append(
                    MealSlot(
                        day=day,
                        meal_type=meal_type,
                        recipe_id="phase1-{meal_type}-{day_index}".format(
                            meal_type=meal_type,
                            day_index=day_index + 1,
                        ),
                        recipe_name=template["recipe_name"],
                        prep_time_min=int(template["prep_time_min"]),
                        calories=calories,
                        protein_g=int(round(nutrition_plan.protein_g * CALORIE_SPLITS[meal_type])),
                        carbs_g=int(round(nutrition_plan.carbs_g * CALORIE_SPLITS[meal_type])),
                        fat_g=int(round(nutrition_plan.fat_g * CALORIE_SPLITS[meal_type])),
                    )
                )
        return plan

    def _pick_template(
        self,
        meal_type: str,
        day_index: int,
        restrictions: set,
        allergies: set,
    ) -> Dict[str, Any]:
        templates = list(MEAL_LIBRARY[meal_type])
        filtered = []
        for template in templates:
            tags = {tag.lower() for tag in template.get("tags", [])}
            name = template["recipe_name"].lower()
            if "vegetarian" in restrictions and "vegetarian" not in tags:
                continue
            if "vegan" in restrictions and "vegan" not in tags:
                continue
            if any(allergen in name for allergen in allergies):
                continue
            filtered.append(template)
        chosen = filtered or templates
        return chosen[day_index % len(chosen)]
