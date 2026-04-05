from __future__ import annotations

import asyncio

from shopper.agents.nodes.price_optimizer import PriceOptimizerNode
from shopper.schemas import GroceryItem, StoreQuote


class StaticAdapter:
    def __init__(self, store_name: str, quotes: list[StoreQuote]) -> None:
        self.store_name = store_name
        self._quotes = quotes

    async def search_prices(self, items):  # noqa: ANN001
        return self._quotes


class FailingAdapter:
    def __init__(self, store_name: str) -> None:
        self.store_name = store_name

    async def search_prices(self, items):  # noqa: ANN001
        raise RuntimeError("temporary outage")


def test_price_optimizer_handles_partial_adapter_failure():
    grocery_item = GroceryItem(
        name="spinach",
        quantity=2.0,
        unit="cup",
        category="produce",
        already_have=False,
        shopping_quantity=2.0,
        quantity_in_fridge=0.0,
        source_recipe_ids=["recipe-1"],
    )
    walmart_quote = StoreQuote(
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
    node = PriceOptimizerNode(
        store_adapters=[
            FailingAdapter("Instacart"),
            StaticAdapter("Walmart", [walmart_quote]),
        ]
    )

    result = asyncio.run(
        node(
            {
                "run_id": "run-1",
                "user_id": "michael",
                "user_profile": {
                    "budget_weekly": 25,
                    "cooking_skill": "intermediate",
                    "goal": "maintain",
                    "schedule_json": {"weeknight_dinner": "30m"},
                },
                "grocery_list": [grocery_item.model_dump(mode="json")],
            }
        )
    )

    assert result["purchase_orders"]
    assert result["budget_summary"]["within_budget"] is True
    assert result["price_rationale"]
    assert "partial store coverage" in result["price_rationale"]


def test_price_optimizer_prefers_affordable_in_store_plan_when_delivery_pushes_over_budget():
    grocery_item = GroceryItem(
        name="yogurt",
        quantity=2.0,
        unit="cup",
        category="dairy",
        already_have=False,
        shopping_quantity=2.0,
        quantity_in_fridge=0.0,
        source_recipe_ids=["recipe-2"],
    )
    walmart_quote = StoreQuote(
        store="Walmart",
        item_name="yogurt",
        requested_quantity=2.0,
        requested_unit="cup",
        price=8.0,
        unit_price=4.0,
        in_stock=True,
        delivery_fee=5.99,
        min_order=22.0,
    )
    node = PriceOptimizerNode(store_adapters=[StaticAdapter("Walmart", [walmart_quote])])

    result = asyncio.run(
        node(
            {
                "run_id": "run-2",
                "user_id": "michael",
                "user_profile": {
                    "budget_weekly": 10,
                    "cooking_skill": "intermediate",
                    "goal": "maintain",
                    "schedule_json": {"weeknight_dinner": "30m"},
                },
                "grocery_list": [grocery_item.model_dump(mode="json")],
            }
        )
    )

    assert result["purchase_orders"][0]["channel"] == "in_store"
    assert result["budget_summary"]["within_budget"] is True
    assert result["budget_summary"]["total_cost"] == 8.0
