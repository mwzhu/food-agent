from __future__ import annotations

from typing import Any

from shopper.schemas import FridgeItemSnapshot, GroceryItem, MealSlot
from shopper.validators import validate_fridge_inventory_consistency, validate_grocery_fridge_diff


class GroceryFridgeDiffEvaluator:
    def evaluate(
        self,
        case: dict[str, Any],
        meals: list[MealSlot],
        grocery_list: list[GroceryItem],
        fridge_inventory: list[FridgeItemSnapshot],
    ) -> dict[str, Any]:
        issues = validate_grocery_fridge_diff(meals, grocery_list, fridge_inventory)
        issues.extend(validate_fridge_inventory_consistency(grocery_list, fridge_inventory))
        return {
            "case_id": case["case_id"],
            "passed": not issues,
            "issues": sorted(set(issues)),
            "already_have_count": sum(1 for item in grocery_list if item.already_have),
        }
