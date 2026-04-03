from __future__ import annotations

from shopper.schemas import MealSlot, NutritionPlan
from shopper.validators import validate_daily_macro_alignment, validate_meal_plan_slot_coverage


def _meal(day: str, meal_type: str, calories: int, protein_g: int, carbs_g: int, fat_g: int) -> MealSlot:
    return MealSlot(
        day=day,
        meal_type=meal_type,  # type: ignore[arg-type]
        recipe_id="{day}-{meal_type}".format(day=day, meal_type=meal_type),
        recipe_name="{day} {meal_type}".format(day=day, meal_type=meal_type),
        cuisine="american",
        prep_time_min=15,
        serving_multiplier=1.0,
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        tags=[],
        macro_fit_score=0.8,
        recipe=None,
    )


def test_slot_coverage_detects_missing_and_duplicate_slots():
    meals = [
        _meal("monday", "breakfast", 400, 30, 35, 10),
        _meal("monday", "breakfast", 420, 31, 35, 10),
        _meal("monday", "lunch", 500, 35, 45, 12),
    ]

    issues = validate_meal_plan_slot_coverage(meals)

    assert "Duplicate meal slot for monday breakfast." in issues
    assert "Missing meal slot for monday dinner." in issues


def test_daily_macro_alignment_flags_large_daily_misses():
    plan = NutritionPlan(
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
    meals = [
        _meal("monday", "breakfast", 800, 40, 60, 20),
        _meal("monday", "lunch", 900, 45, 80, 25),
        _meal("monday", "dinner", 850, 40, 70, 30),
        _meal("monday", "snack", 300, 10, 35, 10),
    ]

    issues = validate_daily_macro_alignment(plan, meals, "eval")

    assert any("Monday calories missed the daily target" in issue for issue in issues)
