from __future__ import annotations

import math
import asyncio
import hashlib
from dataclasses import dataclass
from typing import Protocol, Sequence

from shopper.schemas import GroceryItem, StoreQuote


class StoreAdapter(Protocol):
    store_name: str

    async def search_prices(self, items: Sequence[GroceryItem]) -> list[StoreQuote]:
        ...


@dataclass(frozen=True)
class InstacartAdapter:
    store_name: str = "Instacart"
    delivery_fee: float = 8.99
    min_order: float = 18.0

    async def search_prices(self, items: Sequence[GroceryItem]) -> list[StoreQuote]:
        await asyncio.sleep(0.06)
        return _build_quotes(
            self.store_name,
            items,
            markup=1.18,
            price_bias=1.08,
            delivery_fee=self.delivery_fee,
            min_order=self.min_order,
            stock_floor=0.9,
        )


@dataclass(frozen=True)
class MockWalmartAdapter:
    store_name: str = "Walmart"
    delivery_fee: float = 5.99
    min_order: float = 22.0

    async def search_prices(self, items: Sequence[GroceryItem]) -> list[StoreQuote]:
        await asyncio.sleep(0.04)
        return _build_quotes(
            self.store_name,
            items,
            markup=0.98,
            price_bias=0.92,
            delivery_fee=self.delivery_fee,
            min_order=self.min_order,
            stock_floor=0.94,
        )


@dataclass(frozen=True)
class MockCostcoAdapter:
    store_name: str = "Costco"
    delivery_fee: float = 10.99
    min_order: float = 30.0

    async def search_prices(self, items: Sequence[GroceryItem]) -> list[StoreQuote]:
        await asyncio.sleep(0.05)
        return _build_quotes(
            self.store_name,
            items,
            markup=0.94,
            price_bias=0.86,
            delivery_fee=self.delivery_fee,
            min_order=self.min_order,
            stock_floor=0.88,
            bulk=True,
        )


def default_store_adapters() -> list[StoreAdapter]:
    return [InstacartAdapter(), MockWalmartAdapter(), MockCostcoAdapter()]


def _build_quotes(
    store_name: str,
    items: Sequence[GroceryItem],
    *,
    markup: float,
    price_bias: float,
    delivery_fee: float,
    min_order: float,
    stock_floor: float,
    bulk: bool = False,
) -> list[StoreQuote]:
    quotes: list[StoreQuote] = []

    for item in items:
        requested_quantity = item.shopping_quantity if item.shopping_quantity > 0 else item.quantity
        if item.already_have or requested_quantity <= 0:
            continue

        base_unit_cost = _base_unit_cost(item)
        quantity_multiplier = 0.65 + math.log1p(max(requested_quantity, 0.1)) * 0.24
        hashed_variance = _stable_ratio(store_name, item.name, "price")
        stock_ratio = _stable_ratio(store_name, item.name, "stock")

        effective_markup = markup * (0.92 + hashed_variance * 0.22) * price_bias
        if bulk and item.category in {"pantry", "meat", "frozen"}:
            effective_markup *= 0.9
            quantity_multiplier = max(quantity_multiplier, 0.82 + math.log1p(max(requested_quantity, 0.1)) * 0.26)
        elif bulk and item.category == "produce":
            effective_markup *= 1.06

        price = round(max(0.69, base_unit_cost * quantity_multiplier * effective_markup), 2)
        unit_price = round(price / max(requested_quantity, 1.0), 2)
        in_stock = stock_ratio <= stock_floor

        quotes.append(
            StoreQuote(
                store=store_name,
                item_name=item.name,
                requested_quantity=requested_quantity,
                requested_unit=item.unit,
                price=price,
                unit_price=unit_price,
                in_stock=in_stock,
                delivery_fee=delivery_fee,
                min_order=min_order,
            )
        )

    return quotes


def _base_unit_cost(item: GroceryItem) -> float:
    category_bases = {
        "produce": 0.56,
        "dairy": 0.7,
        "meat": 0.98,
        "pantry": 0.38,
        "frozen": 0.79,
    }
    keyword_adjustments = {
        "salmon": 2.6,
        "shrimp": 2.2,
        "steak": 2.1,
        "chicken": 1.4,
        "beef": 1.8,
        "berries": 1.3,
        "avocado": 1.2,
        "cheese": 1.3,
        "yogurt": 1.2,
        "rice": 0.8,
        "beans": 0.9,
        "pasta": 0.95,
        "oil": 1.15,
        "spice": 0.7,
    }

    normalized_name = item.name.lower()
    base = category_bases.get(item.category, 2.0)
    for keyword, adjustment in keyword_adjustments.items():
        if keyword in normalized_name:
            base *= adjustment
            break
    if item.unit in {"lb", "kg"}:
        base *= 1.2
    if item.unit in {"oz", "g"}:
        base *= 0.82
    return round(base, 2)


def _stable_ratio(*parts: str) -> float:
    digest = hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / float(0xFFFFFFFF)
