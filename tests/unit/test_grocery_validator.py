from __future__ import annotations

from shopper.schemas import GroceryItem, MealSlot, RecipeIngredient, RecipeRecord
from shopper.validators import validate_grocery_aggregation, validate_grocery_traceability


def _meal() -> MealSlot:
    recipe = RecipeRecord(
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
        tags=[],
        instructions=["Cook and serve."],
        source_url=None,
    )
    return MealSlot(
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
        macro_fit_score=0.93,
        recipe=recipe,
    )


def test_grocery_aggregation_flags_duplicate_items():
    meal = _meal()
    grocery_list = [
        GroceryItem(
            name="rice",
            quantity=0.5,
            unit="cup",
            category="pantry",
            already_have=False,
            shopping_quantity=0.5,
            quantity_in_fridge=0.0,
            source_recipe_ids=[meal.recipe_id],
        ),
        GroceryItem(
            name="rice",
            quantity=0.5,
            unit="cup",
            category="pantry",
            already_have=False,
            shopping_quantity=0.5,
            quantity_in_fridge=0.0,
            source_recipe_ids=[meal.recipe_id],
        ),
    ]

    issues = validate_grocery_aggregation([meal], grocery_list)

    assert "Grocery list duplicated item rice." in issues


def test_grocery_traceability_flags_incorrect_source_recipe_ids():
    meal = _meal()
    grocery_list = [
        GroceryItem(
            name="chicken breast",
            quantity=5.0,
            unit="oz",
            category="meat",
            already_have=False,
            shopping_quantity=5.0,
            quantity_in_fridge=0.0,
            source_recipe_ids=["wrong-recipe"],
        )
    ]

    issues = validate_grocery_traceability([meal], grocery_list)

    assert "Grocery item chicken breast has incorrect source recipe ids." in issues
