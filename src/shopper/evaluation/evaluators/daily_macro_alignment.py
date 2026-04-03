from __future__ import annotations

from typing import Any, Dict

from shopper.schemas import MealSlot, NutritionPlan
from shopper.validators import daily_macro_alignment, validate_daily_macro_alignment


class DailyMacroAlignmentEvaluator:
    def evaluate(self, case: Dict[str, Any], plan: NutritionPlan, meals: list[MealSlot]) -> Dict[str, Any]:
        issues = validate_daily_macro_alignment(plan, meals, "eval")
        totals = daily_macro_alignment(meals)
        targets = {
            "calories": float(plan.daily_calories),
            "protein_g": float(plan.protein_g),
            "carbs_g": float(plan.carbs_g),
            "fat_g": float(plan.fat_g),
        }
        delta_pct = {
            day: {
                metric: round(abs(float(values[metric]) - target) / max(target, 1.0), 4)
                for metric, target in targets.items()
            }
            for day, values in totals.items()
        }
        max_delta_pct = {
            metric: round(max((day_values[metric] for day_values in delta_pct.values()), default=0.0), 4)
            for metric in targets
        }
        return {
            "case_id": case["case_id"],
            "passed": not issues,
            "issues": sorted(set(issues)),
            "daily_totals": totals,
            "max_delta_pct": max_delta_pct,
        }
