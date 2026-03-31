from __future__ import annotations

from shopper.schemas import NutritionTargets, ProfileFacts


ACTIVITY_MULTIPLIERS = {
    "low": 1.2,
    "moderate": 1.55,
    "high": 1.725,
}


def calculate_nutrition_targets(profile: ProfileFacts) -> NutritionTargets:
    sex_adjustment = 5 if profile.sex == "male" else -161 if profile.sex == "female" else -78
    bmr = (10 * profile.weight_kg) + (6.25 * profile.height_cm) - (5 * profile.age) + sex_adjustment
    tdee = int(bmr * ACTIVITY_MULTIPLIERS.get(profile.activity_level, 1.55))
    calorie_adjustment = {"cut": -350, "maintain": 0, "bulk": 250}[profile.goal]
    calories = max(1200, tdee + calorie_adjustment)
    protein_g = max(90, int(profile.weight_kg * 1.8))
    fat_g = max(45, int((calories * 0.25) / 9))
    carbs_g = max(100, int((calories - (protein_g * 4) - (fat_g * 9)) / 4))
    fiber_g = 25 if profile.sex == "female" else 30
    return NutritionTargets(
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        fiber_g=fiber_g,
        notes=f"{profile.goal} plan optimized for {profile.weekday_time_limit_minutes}-minute weekdays.",
    )

