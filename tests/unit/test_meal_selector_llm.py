from __future__ import annotations

import asyncio

from shopper.agents.nodes.meal_selector import MealRequest, MealSelectorInputs, MealSelectorNode
from shopper.schemas import NutritionPlan, PreferenceSummary, RecipeIngredient, RecipeRecord
from shopper.schemas.user import UserProfileBase


class FakeRecipeSearchTool:
    def __init__(self, candidates):
        self.candidates = candidates

    async def search(self, query, filters=None, top_k=5, context=None):
        return self.candidates


class FakeStructuredModel:
    def __init__(self, schema, response, calls):
        self.schema = schema
        self.response = response
        self.calls = calls

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return self.schema.model_validate(self.response)


class FakeChatModel:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def with_structured_output(self, schema):
        return FakeStructuredModel(schema=schema, response=self.response, calls=self.calls)


def _recipe(recipe_id: str, name: str, cuisine: str, calories: int, protein_g: int) -> RecipeRecord:
    return RecipeRecord(
        recipe_id=recipe_id,
        name=name,
        cuisine=cuisine,
        meal_types=["lunch"],
        ingredients=[RecipeIngredient(name="chicken breast"), RecipeIngredient(name="rice")],
        prep_time_min=20,
        calories=calories,
        protein_g=protein_g,
        carbs_g=30,
        fat_g=12,
        tags=["high-protein"],
        instructions=["Cook and serve."],
        source_url=None,
    )


def test_meal_selector_uses_llm_choice_for_slot_selection():
    first_recipe = _recipe("first-choice", "Default Bowl", "american", 520, 35)
    llm_recipe = _recipe("llm-choice", "Thai Chicken Bowl", "thai", 500, 36)
    recipe_search = FakeRecipeSearchTool(
        [
            {"recipe": first_recipe.model_dump(mode="json"), "rerank_score": 0.98, "reasons": ["top rank"]},
            {"recipe": llm_recipe.model_dump(mode="json"), "rerank_score": 0.81, "reasons": ["preferred cuisine"]},
        ]
    )
    chat_model = FakeChatModel({"recipe_id": "llm-choice", "rationale": "Thai flavor matches the learned preference."})
    node = MealSelectorNode(context_assembler=None, recipe_search=recipe_search, chat_model=chat_model)
    state = {
        "run_id": "selector-run",
        "user_profile": {
            "age": 31,
            "weight_lbs": 175,
            "height_in": 70,
            "sex": "male",
            "activity_level": "moderately_active",
            "goal": "maintain",
            "dietary_restrictions": [],
            "allergies": [],
            "budget_weekly": 140,
            "household_size": 1,
            "cooking_skill": "intermediate",
            "schedule_json": {"weekdays": "quick"},
        },
        "user_preferences_learned": {"preferred_cuisines": ["thai"], "avoided_ingredients": []},
        "repair_instructions": [],
        "blocked_recipe_ids": [],
        "avoid_cuisines": [],
    }
    profile = UserProfileBase.model_validate(state["user_profile"])
    nutrition_plan = NutritionPlan(
        tdee=2400,
        daily_calories=2400,
        protein_g=180,
        carbs_g=220,
        fat_g=80,
        fiber_g=30,
        goal="maintain",
        applied_restrictions=[],
        notes="",
    )

    meal, decision_source = asyncio.run(
        node._select_meal_for_slot(
            profile=profile,
            nutrition_plan=nutrition_plan,
            slot=MealRequest(
                day="monday",
                day_index=0,
                meal_type="lunch",
                max_prep_time=20,
                query="maintain lunch high protein quick thai",
            ),
            inputs=MealSelectorInputs(
                preferences=PreferenceSummary.model_validate(state["user_preferences_learned"]),
                repair_instructions=[],
                blocked_recipe_ids=set(),
                avoid_cuisines=set(),
            ),
            selected_meals=[],
            prompt_template="Choose from the candidates only.",
            assembled_context={"preference_summary": state["user_preferences_learned"]},
        )
    )

    assert decision_source == "llm"
    assert meal.recipe_id == "llm-choice"
    assert chat_model.calls, "Expected the selector to invoke the chat model."
