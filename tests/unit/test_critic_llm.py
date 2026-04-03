from __future__ import annotations

import asyncio

from shopper.agents.nodes.planning_critic import PlanningCriticNode
from shopper.memory import AssembledContext, ContextBudget
from shopper.schemas import MealSlot, NutritionPlan, RecipeIngredient, RecipeRecord


class FakeContextAssembler:
    async def build_context(self, node_name, state):
        return AssembledContext(
            node_name=node_name,
            payload={"selected_meals": state.get("selected_meals", [])},
            retrieved_memories=[],
            budget=ContextBudget(
                token_budget=1800,
                tokens_used=200,
                fields_included=["selected_meals"],
                fields_dropped=[],
            ),
        )


class FakeRecipeStore:
    def __init__(self, recipes):
        self.recipes = {recipe.recipe_id: recipe for recipe in recipes}

    def get_recipe(self, recipe_id):
        return self.recipes.get(recipe_id)


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


def _recipe() -> RecipeRecord:
    return RecipeRecord(
        recipe_id="chicken-rice-bowl",
        name="Chicken Rice Bowl",
        cuisine="american",
        meal_types=["lunch"],
        ingredients=[RecipeIngredient(name="chicken breast"), RecipeIngredient(name="rice")],
        prep_time_min=18,
        calories=500,
        protein_g=38,
        carbs_g=42,
        fat_g=14,
        tags=["high-protein"],
        instructions=["Cook and serve."],
        source_url=None,
    )


def _nutrition_plan() -> NutritionPlan:
    return NutritionPlan(
        tdee=2300,
        daily_calories=2200,
        protein_g=170,
        carbs_g=210,
        fat_g=70,
        fiber_g=30,
        goal="maintain",
        applied_restrictions=[],
        notes="",
    )


def _state_for_meal(meal: MealSlot, nutrition_plan: NutritionPlan) -> dict:
    return {
        "run_id": "critic-run",
        "user_profile": {
            "age": 30,
            "weight_lbs": 170,
            "height_in": 69,
            "sex": "male",
            "activity_level": "lightly_active",
            "goal": "maintain",
            "dietary_restrictions": [],
            "allergies": [],
            "budget_weekly": 135,
            "household_size": 1,
            "cooking_skill": "intermediate",
            "schedule_json": {"weekdays": "quick"},
        },
        "nutrition_plan": nutrition_plan.model_dump(mode="json"),
        "selected_meals": [meal.model_dump(mode="json")],
    }


def test_critic_includes_llm_review_findings():
    recipe = _recipe()
    nutrition_plan = _nutrition_plan()
    meal = MealSlot(
        day="monday",
        meal_type="lunch",
        recipe_id=recipe.recipe_id,
        recipe_name=recipe.name,
        cuisine=recipe.cuisine,
        prep_time_min=recipe.prep_time_min,
        serving_multiplier=1.0,
        calories=recipe.calories,
        protein_g=recipe.protein_g,
        carbs_g=recipe.carbs_g,
        fat_g=recipe.fat_g,
        tags=recipe.tags,
        macro_fit_score=0.91,
        recipe=recipe,
    )
    chat_model = FakeChatModel(
        {
            "passed": False,
            "issues": ["Weekday lunches still look a little too repetitive."],
            "warnings": ["Cuisine palette leans heavily on one profile."],
            "repair_instructions": ["Swap one lunch for a distinct cuisine with similar macros."],
        }
    )
    node = PlanningCriticNode(
        context_assembler=FakeContextAssembler(),
        recipe_store=FakeRecipeStore([recipe]),
        chat_model=chat_model,
    )

    result = asyncio.run(node(_state_for_meal(meal, nutrition_plan)))

    verdict = result["critic_verdict"]
    assert verdict["passed"] is False
    assert "Weekday lunches still look a little too repetitive." in verdict["issues"]
    assert "Cuisine palette leans heavily on one profile." in verdict["warnings"]
    assert "Swap one lunch for a distinct cuisine with similar macros." in verdict["repair_instructions"]
    assert any(finding["code"] == "P_LLM_REVIEW" for finding in verdict["findings"])
    assert chat_model.calls, "Expected the critic to invoke the chat model."


def test_critic_hard_blockers_override_llm_pass():
    recipe = _recipe()
    nutrition_plan = _nutrition_plan()
    meal = MealSlot(
        day="monday",
        meal_type="lunch",
        recipe_id=recipe.recipe_id,
        recipe_name=recipe.name,
        cuisine=recipe.cuisine,
        prep_time_min=recipe.prep_time_min,
        serving_multiplier=1.0,
        calories=900,
        protein_g=recipe.protein_g,
        carbs_g=recipe.carbs_g,
        fat_g=recipe.fat_g,
        tags=recipe.tags,
        macro_fit_score=0.45,
        recipe=recipe,
    )
    chat_model = FakeChatModel(
        {
            "passed": True,
            "issues": [],
            "warnings": [],
            "repair_instructions": [],
        }
    )
    node = PlanningCriticNode(
        context_assembler=FakeContextAssembler(),
        recipe_store=FakeRecipeStore([recipe]),
        chat_model=chat_model,
    )

    result = asyncio.run(node(_state_for_meal(meal, nutrition_plan)))

    verdict = result["critic_verdict"]
    assert verdict["passed"] is False
    assert any("drifted too far from the recipe source nutrition" in issue for issue in verdict["issues"])
    assert any(finding["code"] == "P_GROUNDEDNESS" for finding in verdict["findings"])
