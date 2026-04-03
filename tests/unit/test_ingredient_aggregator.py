from __future__ import annotations

import pytest

from shopper.schemas import FridgeItemSnapshot
from shopper.services.ingredient_aggregator import (
    AggregatedItem,
    RawIngredient,
    aggregate_quantities,
    convert_quantity,
    diff_against_fridge,
)


def test_aggregate_quantities_combines_duplicate_units() -> None:
    ingredients = [
        RawIngredient(name="milk", quantity=2.0, unit="cup", recipe_id="recipe-a"),
        RawIngredient(name="milk", quantity=1.5, unit="cup", recipe_id="recipe-b"),
    ]

    result = aggregate_quantities(ingredients)

    assert result == [
        AggregatedItem(
            name="milk",
            quantity=3.5,
            unit="cup",
            source_recipe_ids=("recipe-a", "recipe-b"),
        )
    ]


def test_aggregate_quantities_combines_cross_unit_volume_inputs() -> None:
    ingredients = [
        RawIngredient(name="milk", quantity=1.0, unit="cup", recipe_id="recipe-a"),
        RawIngredient(name="milk", quantity=240.0, unit="ml", recipe_id="recipe-b"),
    ]

    result = aggregate_quantities(ingredients)

    assert result == [
        AggregatedItem(
            name="milk",
            quantity=2.0,
            unit="cup",
            source_recipe_ids=("recipe-a", "recipe-b"),
        )
    ]


def test_diff_against_fridge_marks_items_already_owned() -> None:
    items = [
        AggregatedItem(name="milk", quantity=3.5, unit="cup", source_recipe_ids=("recipe-a",)),
    ]
    fridge = [
        FridgeItemSnapshot(
            item_id=1,
            user_id="casey",
            name="milk",
            quantity=4.0,
            unit="cup",
            category="dairy",
            expiry_date=None,
        )
    ]

    result = diff_against_fridge(items, fridge)

    assert len(result) == 1
    assert result[0].already_have is True
    assert result[0].shopping_quantity == 0
    assert result[0].quantity_in_fridge == 3.5


def test_diff_against_fridge_handles_partial_coverage() -> None:
    items = [
        AggregatedItem(name="milk", quantity=2.0, unit="cup", source_recipe_ids=("recipe-a",)),
    ]
    fridge = [
        FridgeItemSnapshot(
            item_id=1,
            user_id="casey",
            name="milk",
            quantity=240.0,
            unit="ml",
            category="dairy",
            expiry_date=None,
        )
    ]

    result = diff_against_fridge(items, fridge)

    assert len(result) == 1
    assert result[0].already_have is False
    assert result[0].shopping_quantity == pytest.approx(1.0, abs=0.01)
    assert result[0].quantity_in_fridge == pytest.approx(1.0, abs=0.01)


def test_diff_against_fridge_with_empty_fridge_keeps_full_quantity() -> None:
    items = [
        AggregatedItem(name="black beans", quantity=1.0, unit="cup", source_recipe_ids=("recipe-a",)),
    ]

    result = diff_against_fridge(items, [])

    assert len(result) == 1
    assert result[0].already_have is False
    assert result[0].shopping_quantity == 1.0
    assert result[0].quantity_in_fridge == 0


def test_unit_conversion_handles_weight_and_volume_edges() -> None:
    assert convert_quantity(56.699, "g", "oz") == pytest.approx(2.0, abs=0.01)
    assert convert_quantity(3.0, "tsp", "tbsp") == pytest.approx(1.0, abs=0.01)
