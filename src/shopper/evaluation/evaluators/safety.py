from __future__ import annotations

from typing import Any, Dict, List

from shopper.schemas import MealSlot
from shopper.validators import validate_meal_plan_safety


class SafetyEvaluator:
    def evaluate(self, case: Dict[str, Any], meals: List[MealSlot]) -> Dict[str, Any]:
        issues = validate_meal_plan_safety(meals, case["profile"].get("allergies", []))
        expected_safe = case.get("expected", {}).get("safe", True)
        if expected_safe and issues:
            issues.append("Safety case expected a clean meal plan.")
        return {"passed": not issues, "issues": sorted(set(issues))}
