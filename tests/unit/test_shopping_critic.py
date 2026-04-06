from __future__ import annotations

import asyncio

from shopper.agents.nodes.shopping_critic import ShoppingCriticNode
from shopper.memory import AssembledContext, ContextBudget
from shopper.schemas import (
    BudgetSummary,
    FridgeItemSnapshot,
    GroceryItem,
    MealSlot,
    PurchaseOrder,
    PurchaseOrderItem,
    RecipeIngredient,
    RecipeRecord,
)


class FakeContextAssembler:
    async def build_context(self, node_name, state):
        return AssembledContext(
            node_name=node_name,
            payload={
                "grocery_list": state.get("grocery_list", []),
                "fridge_inventory": state.get("fridge_inventory", []),
            },
            retrieved_memories=[],
            budget=ContextBudget(
                token_budget=1800,
                tokens_used=180,
                fields_included=["grocery_list", "fridge_inventory"],
                fields_dropped=[],
            ),
        )


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
        recipe_id="sheet-pan-dinner",
        name="Sheet Pan Dinner",
        cuisine="american",
        meal_types=["dinner"],
        ingredients=[
            RecipeIngredient(name="chicken breast", quantity=5, unit="oz"),
            RecipeIngredient(name="rice", quantity=1, unit="cup"),
        ],
        prep_time_min=25,
        calories=520,
        protein_g=42,
        carbs_g=48,
        fat_g=12,
        tags=["high-protein"],
        instructions=["Cook and serve."],
        source_url=None,
    )


def test_shopping_critic_includes_llm_findings_on_valid_grocery_list():
    recipe = _recipe()
    meal = MealSlot(
        day="monday",
        meal_type="dinner",
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
        macro_fit_score=0.94,
        recipe=recipe,
    )
    grocery_list = [
        GroceryItem(
            name="chicken breast",
            quantity=5.0,
            unit="oz",
            category="meat",
            already_have=False,
            shopping_quantity=5.0,
            quantity_in_fridge=0.0,
            source_recipe_ids=[recipe.recipe_id],
        ),
        GroceryItem(
            name="rice",
            quantity=1.0,
            unit="cup",
            category="pantry",
            already_have=False,
            shopping_quantity=1.0,
            quantity_in_fridge=0.0,
            source_recipe_ids=[recipe.recipe_id],
        ),
    ]
    chat_model = FakeChatModel(
        {
            "passed": True,
            "issues": [],
            "warnings": ["Quantities look a little tight if leftovers matter."],
            "repair_instructions": [],
        }
    )
    node = ShoppingCriticNode(context_assembler=FakeContextAssembler(), chat_model=chat_model)
    purchase_orders = [
        PurchaseOrder(
            store="Walmart",
            items=[
                PurchaseOrderItem(
                    name="chicken breast",
                    quantity=5.0,
                    unit="oz",
                    category="meat",
                    source_recipe_ids=[recipe.recipe_id],
                    price=6.0,
                    unit_price=1.2,
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
            subtotal=8.5,
            delivery_fee=0.0,
            total_cost=8.5,
            channel="in_store",
            status="pending",
        )
    ]
    budget_summary = BudgetSummary(
        budget=135.0,
        total_cost=8.5,
        overage=0.0,
        within_budget=True,
        utilization=0.06,
    )

    result = asyncio.run(
        node(
            {
                "run_id": "shopping-critic-run",
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
                "selected_meals": [meal.model_dump(mode="json")],
                "grocery_list": [item.model_dump(mode="json") for item in grocery_list],
                "fridge_inventory": [
                    FridgeItemSnapshot(
                        item_id=1,
                        user_id="user-1",
                        name="spinach",
                        quantity=2.0,
                        unit="cup",
                        category="produce",
                        expiry_date=None,
                    ).model_dump(mode="json")
                ],
                "purchase_orders": [order.model_dump(mode="json") for order in purchase_orders],
                "budget_summary": budget_summary.model_dump(mode="json"),
            }
        )
    )

    verdict = result["critic_verdict"]
    assert verdict["passed"] is True
    assert "Quantities look a little tight if leftovers matter." in verdict["warnings"]
    assert any(finding["code"] == "S_LLM_REVIEW" for finding in verdict["findings"])
    assert chat_model.calls


def test_shopping_critic_blocks_missing_purchase_order_coverage():
    recipe = _recipe()
    meal = MealSlot(
        day="monday",
        meal_type="dinner",
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
        macro_fit_score=0.94,
        recipe=recipe,
    )
    grocery_list = [
        GroceryItem(
            name="chicken breast",
            quantity=5.0,
            unit="oz",
            category="meat",
            already_have=False,
            shopping_quantity=5.0,
            quantity_in_fridge=0.0,
            source_recipe_ids=[recipe.recipe_id],
        )
    ]
    node = ShoppingCriticNode(context_assembler=FakeContextAssembler(), chat_model=None)

    result = asyncio.run(
        node(
            {
                "run_id": "shopping-critic-run",
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
                "selected_meals": [meal.model_dump(mode="json")],
                "grocery_list": [item.model_dump(mode="json") for item in grocery_list],
                "purchase_orders": [],
                "budget_summary": {
                    "budget": 135.0,
                    "total_cost": 0.0,
                    "overage": 0.0,
                    "within_budget": True,
                    "utilization": 0.0,
                },
            }
        )
    )

    verdict = result["critic_verdict"]
    assert verdict["passed"] is False
    assert "Missing purchase order coverage for 'chicken breast'." in verdict["issues"]
    assert any(finding["code"] == "S_PRICE_COVERAGE" for finding in verdict["findings"])
