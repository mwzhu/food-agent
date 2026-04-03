from __future__ import annotations

from typing import Any

from shopper.schemas import GroceryItem, MealSlot
from shopper.validators import validate_grocery_traceability


class GroceryTraceabilityEvaluator:
    def evaluate(
        self,
        case: dict[str, Any],
        meals: list[MealSlot],
        grocery_list: list[GroceryItem],
    ) -> dict[str, Any]:
        issues = validate_grocery_traceability(meals, grocery_list)
        return {
            "case_id": case["case_id"],
            "passed": not issues,
            "issues": sorted(set(issues)),
        }
