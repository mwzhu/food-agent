from __future__ import annotations

from typing import Iterable

from shopper.schemas import FridgeItemSnapshot, GroceryItem, MealSlot
from shopper.services.ingredient_aggregator import (
    AggregatedItem,
    aggregate_quantities,
    build_fridge_index,
    canonicalize_name,
    categorize,
    comparable_unit,
    diff_against_fridge,
    extract_ingredients,
    quantity_to_comparable,
)


def validate_grocery_list(
    meals: Iterable[MealSlot],
    grocery_list: Iterable[GroceryItem],
) -> list[str]:
    expected_by_key = _expected_by_key(meals)
    actual_by_key = {
        (canonicalize_name(item.name), comparable_unit(item.unit)): item
        for item in grocery_list
    }

    issues: list[str] = []
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


def validate_grocery_aggregation(
    meals: Iterable[MealSlot],
    grocery_list: Iterable[GroceryItem],
) -> list[str]:
    issues: list[str] = []
    expected_by_key = _expected_by_key(meals)
    actual_items = list(grocery_list)
    duplicate_counts: dict[tuple[str, str | None], int] = {}
    aggregated_actual_totals: dict[tuple[str, str | None], float] = {}

    for item in actual_items:
        key = (canonicalize_name(item.name), comparable_unit(item.unit))
        duplicate_counts[key] = duplicate_counts.get(key, 0) + 1
        actual_total, _ = quantity_to_comparable(item.quantity, item.unit)
        aggregated_actual_totals[key] = aggregated_actual_totals.get(key, 0.0) + actual_total

    for key, count in duplicate_counts.items():
        if count > 1:
            issues.append("Grocery list duplicated item {name}.".format(name=key[0]))

    for key, expected in expected_by_key.items():
        actual_total = aggregated_actual_totals.get(key)
        if actual_total is None:
            continue
        expected_total, _ = quantity_to_comparable(expected.quantity, expected.unit)
        if abs(actual_total - expected_total) > 1e-6:
            if actual_total > expected_total:
                issues.append("Grocery item {name} is over-counted.".format(name=expected.name))
            else:
                issues.append("Grocery item {name} did not aggregate to the required quantity.".format(name=expected.name))

    return issues


def validate_grocery_fridge_diff(
    meals: Iterable[MealSlot],
    grocery_list: Iterable[GroceryItem],
    fridge_inventory: Iterable[FridgeItemSnapshot],
) -> list[str]:
    expected_items = categorize(
        diff_against_fridge(
            aggregate_quantities(extract_ingredients(meals)),
            fridge_inventory,
        )
    )
    expected_by_key = {
        (canonicalize_name(item.name), comparable_unit(item.unit)): item
        for item in expected_items
    }
    actual_by_key = {
        (canonicalize_name(item.name), comparable_unit(item.unit)): item
        for item in grocery_list
    }

    issues: list[str] = []
    for key, expected in expected_by_key.items():
        actual = actual_by_key.get(key)
        if actual is None:
            continue

        if actual.already_have != expected.already_have:
            issues.append("Grocery item {name} has the wrong already-have flag.".format(name=expected.name))
        if round(float(actual.shopping_quantity), 2) != round(float(expected.shopping_quantity), 2):
            issues.append("Grocery item {name} has the wrong shopping quantity.".format(name=expected.name))
        if round(float(actual.quantity_in_fridge), 2) != round(float(expected.quantity_in_fridge), 2):
            issues.append("Grocery item {name} has the wrong fridge quantity.".format(name=expected.name))

    return issues


def validate_grocery_traceability(
    meals: Iterable[MealSlot],
    grocery_list: Iterable[GroceryItem],
) -> list[str]:
    expected_by_key = _expected_by_key(meals)
    issues: list[str] = []

    for item in grocery_list:
        key = (canonicalize_name(item.name), comparable_unit(item.unit))
        expected = expected_by_key.get(key)
        if expected is None:
            continue
        expected_source_ids = set(expected.source_recipe_ids)
        actual_source_ids = set(item.source_recipe_ids)
        if not actual_source_ids:
            issues.append("Grocery item {name} is missing source recipe ids.".format(name=item.name))
            continue
        if actual_source_ids != expected_source_ids:
            issues.append("Grocery item {name} has incorrect source recipe ids.".format(name=item.name))

    return issues


def validate_fridge_inventory_consistency(
    grocery_list: Iterable[GroceryItem],
    fridge_inventory: Iterable[FridgeItemSnapshot],
) -> list[str]:
    fridge_index = build_fridge_index(fridge_inventory)
    issues: list[str] = []
    for item in grocery_list:
        comparable_quantity, comparable = quantity_to_comparable(item.quantity_in_fridge, item.unit)
        available_quantity = fridge_index.get((canonicalize_name(item.name), comparable), 0.0)
        if comparable_quantity - available_quantity > 1e-6:
            issues.append("Grocery item {name} claims more fridge inventory than is available.".format(name=item.name))
    return issues


def _expected_by_key(meals: Iterable[MealSlot]) -> dict[tuple[str, str | None], AggregatedItem]:
    return {
        (canonicalize_name(item.name), comparable_unit(item.unit)): item
        for item in aggregate_quantities(extract_ingredients(meals))
    }
