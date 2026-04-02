from __future__ import annotations

from shopper.schemas import MealSlot, RecipeIngredient, RecipeRecord
from shopper.validators import validate_meal_plan_safety


def test_safety_validator_catches_peanut_oil_for_nut_allergy():
    meal = MealSlot(
        day="monday",
        meal_type="dinner",
        recipe_id="unsafe-stir-fry",
        recipe_name="Unsafe Stir Fry",
        cuisine="asian",
        prep_time_min=20,
        serving_multiplier=1.0,
        calories=520,
        protein_g=26,
        carbs_g=40,
        fat_g=18,
        tags=[],
        macro_fit_score=0.7,
        recipe=RecipeRecord(
            recipe_id="unsafe-stir-fry",
            name="Unsafe Stir Fry",
            cuisine="asian",
            meal_types=["dinner"],
            ingredients=[
                RecipeIngredient(name="chicken breast", quantity=5, unit="oz"),
                RecipeIngredient(name="peanut oil", quantity=1, unit="tbsp"),
            ],
            prep_time_min=20,
            calories=520,
            protein_g=26,
            carbs_g=40,
            fat_g=18,
            tags=[],
            instructions=["Cook everything together."],
            source_url=None,
        ),
    )

    issues = validate_meal_plan_safety([meal], ["peanut"])

    assert issues
    assert "Allergen 'peanut'" in issues[0]
