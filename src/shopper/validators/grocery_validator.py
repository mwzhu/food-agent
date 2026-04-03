from __future__ import annotations

from typing import Iterable, List

from shopper.schemas import GroceryItem, MealSlot
from shopper.services.ingredient_aggregator import (
    aggregate_quantities,
    canonicalize_name,
    comparable_unit,
    extract_ingredients,
    quantity_to_comparable,
)


def validate_grocery_list(
    meals: Iterable[MealSlot],
    grocery_list: Iterable[GroceryItem],
) -> List[str]:
    expected_items = aggregate_quantities(extract_ingredients(meals))
    expected_by_key = {
        (canonicalize_name(item.name), comparable_unit(item.unit)): item
        for item in expected_items
    }
    actual_by_key = {
        (canonicalize_name(item.name), comparable_unit(item.unit)): item
        for item in grocery_list
    }

    issues: List[str] = []
    for key, expected in expected_by_key.items():
        actual = actual_by_key.get(key)
        if actual is None:
            issues.append("Missing grocery item for {name}.".format(name=expected.name))
            continue
        actual_total, _ = quantity_to_comparable(actual.quantity, actual.unit)
        expected_total, _ = quantity_to_comparable(expected.quantity, expected.unit)
        if actual_total + 1e-6 < expected_total:
            issues.append("Grocery item {name} is under-counted.".format(name=expected.name))

    for key, actual in actual_by_key.items():
        if key not in expected_by_key:
            issues.append("Grocery list contains phantom item {name}.".format(name=actual.name))

    return issues
