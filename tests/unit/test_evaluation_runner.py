from __future__ import annotations

import asyncio

from shopper.config import Settings
from shopper.evaluation.runner import EvaluationRunner
from shopper.schemas import RecipeIngredient, RecipeRecord


class FakeRecipeStore:
    def __init__(self):
        recipe = RecipeRecord(
            recipe_id="sheet-pan-dinner",
            name="Sheet Pan Dinner",
            cuisine="american",
            meal_types=["dinner"],
            ingredients=[RecipeIngredient(name="chicken breast", quantity=5.0, unit="oz")],
            prep_time_min=25,
            calories=520,
            protein_g=42,
            carbs_g=48,
            fat_g=12,
            tags=[],
            instructions=["Cook and serve."],
            source_url=None,
        )
        self.recipes = {recipe.recipe_id: recipe}

    def get_recipe(self, recipe_id):
        return self.recipes.get(recipe_id)


def test_grocery_eval_builds_deterministic_grocery_list_without_graph_invocation():
    runner = EvaluationRunner(
        graph=object(),
        settings=Settings(SHOPPER_APP_ENV="test", LANGSMITH_TRACING=False),
        recipe_store=FakeRecipeStore(),
    )
    case = {
        "case_id": "grocery-prep-case",
        "meal_plan": [
            {
                "day": "monday",
                "meal_type": "dinner",
                "recipe_id": "sheet-pan-dinner",
                "serving_multiplier": 1.0,
            }
        ],
        "fridge_inventory": [],
        "expected": {
            "total_items": 1,
            "already_have_count": 0,
            "items": [
                {
                    "name": "chicken breast",
                    "quantity": 5.0,
                    "unit": "oz",
                    "category": "meat",
                    "already_have": False,
                    "shopping_quantity": 5.0,
                    "quantity_in_fridge": 0.0,
                }
            ],
        },
    }
    runner._load_cases = lambda _: [case]  # type: ignore[method-assign]

    result = asyncio.run(runner.run("grocery_completeness"))

    assert result["passed"] is True
    assert result["results"][0]["trace_metadata"]["kind"] == "deterministic_component"
    assert result["results"][0]["grocery_list"][0]["name"] == "chicken breast"
