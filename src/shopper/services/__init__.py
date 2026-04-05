"""Deterministic services used across planner phases."""

from shopper.services.ingredient_aggregator import (
    AggregatedItem,
    RawIngredient,
    aggregate_quantities,
    categorize,
    convert_quantity,
    diff_against_fridge,
    extract_ingredients,
)
from shopper.services.budget_checker import check_budget
from shopper.services.nutrition_calc import GOAL_MACRO_SPLITS, calculate_macros, calculate_tdee
from shopper.services.price_ranker import (
    PricingSelection,
    build_purchase_orders,
    build_single_store_selection,
    build_split_selection,
    calculate_store_totals,
    missing_priced_items,
    rank_by_price,
    total_order_cost,
)

__all__ = [
    "AggregatedItem",
    "GOAL_MACRO_SPLITS",
    "PricingSelection",
    "RawIngredient",
    "aggregate_quantities",
    "build_purchase_orders",
    "build_single_store_selection",
    "build_split_selection",
    "calculate_macros",
    "calculate_store_totals",
    "calculate_tdee",
    "categorize",
    "check_budget",
    "convert_quantity",
    "diff_against_fridge",
    "extract_ingredients",
    "missing_priced_items",
    "rank_by_price",
    "total_order_cost",
]
