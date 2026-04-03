from __future__ import annotations

from typing import Any, Optional

from shopper.schemas import GroceryItem, MealSlot
from shopper.services.ingredient_aggregator import canonicalize_name, normalize_unit
from shopper.validators import validate_grocery_list


class GroceryCompletenessEvaluator:
    def evaluate(
        self,
        case: dict[str, Any],
        meals: list[MealSlot],
        grocery_list: list[GroceryItem],
    ) -> dict[str, Any]:
        issues = validate_grocery_list(meals, grocery_list)
        if not grocery_list:
            issues.append("Grocery list was empty.")

        expected = case["expected"]
        issues.extend(self._compare_against_expected(grocery_list, expected))

        already_have_count = sum(1 for item in grocery_list if item.already_have)
        categories = sorted({item.category for item in grocery_list})
        return {
            "case_id": case["case_id"],
            "passed": not issues,
            "issues": issues,
            "grocery_item_count": len(grocery_list),
            "already_have_count": already_have_count,
            "categories": categories,
        }

    def _compare_against_expected(
        self,
        grocery_list: list[GroceryItem],
        expected: dict[str, Any],
    ) -> list[str]:
        issues: list[str] = []
        expected_items = expected["items"]
        expected_by_key = {
            self._item_key(item["name"], item["unit"]): item
            for item in expected_items
        }
        actual_by_key = {
            self._item_key(item.name, item.unit): item
            for item in grocery_list
        }

        if len(grocery_list) != expected["total_items"]:
            issues.append(
                "Expected {expected_count} grocery items but got {actual_count}.".format(
                    expected_count=expected["total_items"],
                    actual_count=len(grocery_list),
                )
            )

        actual_already_have = sum(1 for item in grocery_list if item.already_have)
        if actual_already_have != expected["already_have_count"]:
            issues.append(
                "Expected {expected_count} already-owned items but got {actual_count}.".format(
                    expected_count=expected["already_have_count"],
                    actual_count=actual_already_have,
                )
            )

        for key, expected_item in expected_by_key.items():
            actual_item = actual_by_key.get(key)
            if actual_item is None:
                issues.append("Missing expected grocery item {name}.".format(name=expected_item["name"]))
                continue

            for field_name in (
                "quantity",
                "category",
                "already_have",
                "shopping_quantity",
                "quantity_in_fridge",
            ):
                expected_value = expected_item[field_name]
                actual_value = getattr(actual_item, field_name)
                if isinstance(expected_value, float):
                    if round(float(actual_value), 2) != round(float(expected_value), 2):
                        issues.append(
                            "{name} expected {field}={expected_value} but got {actual_value}.".format(
                                name=expected_item["name"],
                                field=field_name,
                                expected_value=expected_value,
                                actual_value=round(float(actual_value), 2),
                            )
                        )
                elif actual_value != expected_value:
                    issues.append(
                        "{name} expected {field}={expected_value} but got {actual_value}.".format(
                            name=expected_item["name"],
                            field=field_name,
                            expected_value=expected_value,
                            actual_value=actual_value,
                        )
                    )

        for key, actual_item in actual_by_key.items():
            if key not in expected_by_key:
                issues.append("Unexpected grocery item {name}.".format(name=actual_item.name))

        return issues

    def _item_key(self, name: str, unit: Optional[str]) -> tuple[str, Optional[str]]:
        return canonicalize_name(name), normalize_unit(unit)
