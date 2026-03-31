from shopper.schemas.common import NutritionPlan
from shopper.validators import validate_nutrition_plan


def test_nutrition_validator_flags_invalid_bounds():
    invalid_plan = NutritionPlan(
        tdee=900,
        daily_calories=900,
        protein_g=0,
        carbs_g=10,
        fat_g=0,
        fiber_g=5,
        goal="cut",
        applied_restrictions=[],
        notes="",
    )

    issues = validate_nutrition_plan(invalid_plan)
    assert "TDEE must be at least 1000 calories." in issues
    assert "Protein must be positive." in issues
