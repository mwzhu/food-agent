from shopper.schemas.user import UserProfileBase
from shopper.services.nutrition_calc import GOAL_MACRO_SPLITS, calculate_macros, calculate_tdee


def test_calculate_tdee_matches_hand_computed_value():
    profile = UserProfileBase(
        age=30,
        weight_lbs=180,
        height_in=70,
        sex="male",
        activity_level="moderately_active",
        goal="maintain",
        dietary_restrictions=[],
        allergies=[],
        budget_weekly=150.0,
        household_size=1,
        cooking_skill="intermediate",
        schedule_json={},
    )

    assert calculate_tdee(profile) == 2763


def test_calculate_macros_uses_goal_split_percentages():
    for goal, split in GOAL_MACRO_SPLITS.items():
        plan = calculate_macros(tdee=2400, goal=goal, sex="female")
        protein_ratio = round((plan.protein_g * 4) / float(plan.daily_calories), 2)
        carbs_ratio = round((plan.carbs_g * 4) / float(plan.daily_calories), 2)
        fat_ratio = round((plan.fat_g * 9) / float(plan.daily_calories), 2)

        assert abs(protein_ratio - split["protein"]) <= 0.02
        assert abs(carbs_ratio - split["carbs"]) <= 0.02
        assert abs(fat_ratio - split["fat"]) <= 0.02
