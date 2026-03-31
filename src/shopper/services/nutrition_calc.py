from __future__ import annotations

from typing import Dict

from shopper.schemas.common import NutritionPlan
from shopper.schemas.user import UserProfileBase


ACTIVITY_MULTIPLIERS: Dict[str, float] = {
    "sedentary": 1.2,
    "lightly_active": 1.375,
    "moderately_active": 1.55,
    "very_active": 1.725,
    "extra_active": 1.9,
}

GOAL_CALORIE_ADJUSTMENTS: Dict[str, float] = {
    "cut": 0.85,
    "maintain": 1.0,
    "bulk": 1.1,
}

GOAL_MACRO_SPLITS: Dict[str, Dict[str, float]] = {
    "cut": {"protein": 0.40, "carbs": 0.30, "fat": 0.30},
    "maintain": {"protein": 0.30, "carbs": 0.35, "fat": 0.35},
    "bulk": {"protein": 0.30, "carbs": 0.40, "fat": 0.30},
}


def calculate_tdee(profile: UserProfileBase) -> int:
    weight_kg = profile.weight_lbs * 0.45359237
    height_cm = profile.height_in * 2.54
    sex_adjustment = 5 if profile.sex == "male" else -161 if profile.sex == "female" else -78
    bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * profile.age) + sex_adjustment
    activity_multiplier = ACTIVITY_MULTIPLIERS[profile.activity_level]
    return int(round(bmr * activity_multiplier))


def calculate_macros(tdee: int, goal: str, sex: str) -> NutritionPlan:
    daily_calories = int(round(max(1200, tdee * GOAL_CALORIE_ADJUSTMENTS[goal])))
    split = GOAL_MACRO_SPLITS[goal]
    protein_g = int(round((daily_calories * split["protein"]) / 4))
    carbs_g = int(round((daily_calories * split["carbs"]) / 4))
    fat_g = int(round((daily_calories * split["fat"]) / 9))
    fiber_baseline = 25 if sex == "female" else 30 if sex == "male" else 28
    fiber_g = max(fiber_baseline, int(round(daily_calories / 1000.0 * 14)))
    return NutritionPlan(
        tdee=tdee,
        daily_calories=daily_calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        fiber_g=fiber_g,
        goal=goal,
        applied_restrictions=[],
        notes="",
    )
