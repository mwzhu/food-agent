from __future__ import annotations

import asyncio

from shopper.agents.nodes.planning_critic import PlanningCriticNode
from shopper.memory import AssembledContext, ContextBudget
from shopper.schemas import (
    BudgetSummary,
    GroceryItem,
    MealSlot,
    NutritionPlan,
    PurchaseOrder,
    PurchaseOrderItem,
    RecipeIngredient,
    RecipeRecord,
    StoreSummary,
)


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


def test_critic_includes_upstream_purchase_and_budget_findings():
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
    node = PlanningCriticNode(
        context_assembler=FakeContextAssembler(),
        recipe_store=FakeRecipeStore([recipe]),
        chat_model=None,
    )

    result = asyncio.run(
        node(
            {
                **_state_for_meal(meal, nutrition_plan),
                "grocery_list": [
                    GroceryItem(
                        name="chicken breast",
                        quantity=1.0,
                        unit="lb",
                        category="meat",
                        already_have=False,
                        shopping_quantity=1.0,
                        quantity_in_fridge=0.0,
                        source_recipe_ids=[recipe.recipe_id],
                    ).model_dump(mode="json")
                ],
                "store_summaries": [
                    StoreSummary(
                        store="Walmart",
                        item_count=1,
                        available_item_count=1,
                        subtotal=12.0,
                        delivery_fee=0.0,
                        total=12.0,
                        min_order=0.0,
                        all_items_available=True,
                        meets_min_order=True,
                    ).model_dump(mode="json")
                ],
                "purchase_orders": [],
                "budget_summary": BudgetSummary(
                    budget=10.0,
                    total_cost=12.0,
                    overage=2.0,
                    within_budget=False,
                    utilization=1.2,
                ).model_dump(mode="json"),
                "price_strategy": "single_store_in_store",
            }
        )
    )

    verdict = result["critic_verdict"]
    assert verdict["passed"] is False
    assert "Missing purchase order coverage for 'chicken breast'." in verdict["issues"]
    assert "Optimized purchase orders exceed the weekly budget by $2.00." in verdict["issues"]
    assert any(finding["code"] == "P_PURCHASE_COVERAGE" for finding in verdict["findings"])
    assert any(finding["code"] == "P_BUDGET" for finding in verdict["findings"])


def test_critic_warns_when_store_channel_choice_looks_inconvenient():
    recipe = _recipe()
    nutrition_plan = NutritionPlan(
        tdee=600,
        daily_calories=500,
        protein_g=38,
        carbs_g=42,
        fat_g=14,
        fiber_g=8,
        goal="maintain",
        applied_restrictions=[],
        notes="",
    )
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
    order = PurchaseOrder(
        store="Walmart",
        items=[
            PurchaseOrderItem(
                name="chicken breast",
                quantity=1.0,
                unit="lb",
                category="meat",
                source_recipe_ids=[recipe.recipe_id],
                price=8.0,
                unit_price=8.0,
            ),
            PurchaseOrderItem(
                name="rice",
                quantity=1.0,
                unit="cup",
                category="pantry",
                source_recipe_ids=[recipe.recipe_id],
                price=2.5,
                unit_price=2.5,
            ),
        ],
        subtotal=10.5,
        delivery_fee=0.0,
        total_cost=10.5,
        channel="in_store",
        status="pending",
    )
    node = PlanningCriticNode(
        context_assembler=FakeContextAssembler(),
        recipe_store=FakeRecipeStore([recipe]),
        chat_model=None,
    )

    result = asyncio.run(
        node(
            {
                **_state_for_meal(meal, nutrition_plan),
                "grocery_list": [
                    GroceryItem(
                        name="chicken breast",
                        quantity=1.0,
                        unit="lb",
                        category="meat",
                        already_have=False,
                        shopping_quantity=1.0,
                        quantity_in_fridge=0.0,
                        source_recipe_ids=[recipe.recipe_id],
                    ).model_dump(mode="json"),
                    GroceryItem(
                        name="rice",
                        quantity=1.0,
                        unit="cup",
                        category="pantry",
                        already_have=False,
                        shopping_quantity=1.0,
                        quantity_in_fridge=0.0,
                        source_recipe_ids=[recipe.recipe_id],
                    ).model_dump(mode="json"),
                ],
                "store_summaries": [
                    StoreSummary(
                        store="Walmart",
                        item_count=2,
                        available_item_count=2,
                        subtotal=10.5,
                        delivery_fee=5.99,
                        total=16.49,
                        min_order=0.0,
                        all_items_available=True,
                        meets_min_order=True,
                    ).model_dump(mode="json")
                ],
                "purchase_orders": [order.model_dump(mode="json")],
                "budget_summary": BudgetSummary(
                    budget=40.0,
                    total_cost=10.5,
                    overage=0.0,
                    within_budget=True,
                    utilization=0.26,
                ).model_dump(mode="json"),
                "price_strategy": "single_store_in_store",
            }
        )
    )

    verdict = result["critic_verdict"]
    assert any("time-constrained schedule" in warning for warning in verdict["warnings"])
    assert any(finding["code"] == "P_STORE_CHOICE" for finding in verdict["findings"])
