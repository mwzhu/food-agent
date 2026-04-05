from __future__ import annotations

from shopper.schemas import GroceryItem, StoreQuote
from shopper.services import build_purchase_orders, build_split_selection, calculate_store_totals, rank_by_price


def test_rank_by_price_chooses_cheapest_in_stock_quote():
    items = [
        GroceryItem(
            name="spinach",
            quantity=2.0,
            unit="cup",
            category="produce",
            already_have=False,
            shopping_quantity=2.0,
            quantity_in_fridge=0.0,
            source_recipe_ids=["recipe-1"],
        )
    ]
    quotes = {
        "Instacart": [
            StoreQuote(
                store="Instacart",
                item_name="spinach",
                requested_quantity=2.0,
                requested_unit="cup",
                price=5.4,
                unit_price=2.7,
                in_stock=True,
                delivery_fee=8.99,
                min_order=18.0,
            )
        ],
        "Walmart": [
            StoreQuote(
                store="Walmart",
                item_name="spinach",
                requested_quantity=2.0,
                requested_unit="cup",
                price=3.8,
                unit_price=1.9,
                in_stock=True,
                delivery_fee=5.99,
                min_order=22.0,
            )
        ],
    }

    ranked = rank_by_price(items, quotes)

    assert ranked[0].best_store == "Walmart"
    assert ranked[0].best_price == 3.8


def test_calculate_store_totals_and_purchase_orders_use_selected_quotes():
    items = [
        GroceryItem(
            name="spinach",
            quantity=2.0,
            unit="cup",
            category="produce",
            already_have=False,
            shopping_quantity=2.0,
            quantity_in_fridge=0.0,
            source_recipe_ids=["recipe-1"],
        ),
        GroceryItem(
            name="yogurt",
            quantity=1.0,
            unit="cup",
            category="dairy",
            already_have=False,
            shopping_quantity=1.0,
            quantity_in_fridge=0.0,
            source_recipe_ids=["recipe-2"],
        ),
    ]
    quotes = {
        "Instacart": [
            StoreQuote(
                store="Instacart",
                item_name="spinach",
                requested_quantity=2.0,
                requested_unit="cup",
                price=5.4,
                unit_price=2.7,
                in_stock=True,
                delivery_fee=8.99,
                min_order=18.0,
            ),
            StoreQuote(
                store="Instacart",
                item_name="yogurt",
                requested_quantity=1.0,
                requested_unit="cup",
                price=4.2,
                unit_price=4.2,
                in_stock=True,
                delivery_fee=8.99,
                min_order=18.0,
            ),
        ],
        "Walmart": [
            StoreQuote(
                store="Walmart",
                item_name="spinach",
                requested_quantity=2.0,
                requested_unit="cup",
                price=3.8,
                unit_price=1.9,
                in_stock=True,
                delivery_fee=5.99,
                min_order=22.0,
            ),
            StoreQuote(
                store="Walmart",
                item_name="yogurt",
                requested_quantity=1.0,
                requested_unit="cup",
                price=3.4,
                unit_price=3.4,
                in_stock=True,
                delivery_fee=5.99,
                min_order=22.0,
            ),
        ],
    }

    ranked = rank_by_price(items, quotes)
    summaries = calculate_store_totals(ranked, quotes)
    walmart_summary = next(summary for summary in summaries if summary.store == "Walmart")
    assert walmart_summary.total == 13.19
    assert walmart_summary.all_items_available is True

    selection = build_split_selection(ranked)
    orders = build_purchase_orders(ranked, quotes, selection)

    assert len(orders) == 1
    assert orders[0].store == "Walmart"
    assert orders[0].total_cost == 13.19
    assert [item.name for item in orders[0].items] == ["spinach", "yogurt"]
