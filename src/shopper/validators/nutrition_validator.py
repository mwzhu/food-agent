from __future__ import annotations

from shopper.schemas.common import NutritionPlan


def validate_nutrition_plan(plan: NutritionPlan) -> list[str]:
    issues = []
    if plan.tdee < 1000:
        issues.append("TDEE must be at least 1000 calories.")
    if plan.daily_calories < 1000:
        issues.append("Daily calories must be at least 1000.")
    if plan.protein_g <= 0:
        issues.append("Protein must be positive.")
    if plan.carbs_g <= 0:
        issues.append("Carbs must be positive.")
    if plan.fat_g <= 0:
        issues.append("Fat must be positive.")

    macro_calories = (plan.protein_g * 4) + (plan.carbs_g * 4) + (plan.fat_g * 9)
    allowed_delta = max(150, int(plan.daily_calories * 0.1))
    if abs(macro_calories - plan.daily_calories) > allowed_delta:
        issues.append("Macro calories must stay within 10 percent of daily calories.")

    return issues
