from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Sequence

from shopper.schemas import GroceryItem, PurchaseOrder, PurchaseOrderItem, StoreQuote, StoreSummary


@dataclass(frozen=True)
class PricingSelection:
    item_store_map: Dict[str, str]
    channels_by_store: Dict[str, str]


def rank_by_price(
    items: Iterable[GroceryItem],
    quotes: Mapping[str, Sequence[StoreQuote]],
) -> list[GroceryItem]:
    ranked_items: list[GroceryItem] = []

    for item in items:
        if item.already_have or item.shopping_quantity <= 0:
            ranked_items.append(item.model_copy(update={"best_store": None, "best_price": 0.0, "buy_online": None}))
            continue

        candidates = [quote for quote in _quotes_for_item(quotes, item) if quote.in_stock]
        if not candidates:
            ranked_items.append(item.model_copy(update={"best_store": None, "best_price": None, "buy_online": None}))
            continue

        best_quote = min(candidates, key=lambda quote: (quote.price, quote.store))
        ranked_items.append(
            item.model_copy(
                update={
                    "best_store": best_quote.store,
                    "best_price": round(best_quote.price, 2),
                }
            )
        )

    return ranked_items


def calculate_store_totals(
    items: Iterable[GroceryItem],
    quotes: Mapping[str, Sequence[StoreQuote]],
) -> list[StoreSummary]:
    purchasable_items = [item for item in items if not item.already_have and item.shopping_quantity > 0]
    quote_lookup = _quote_lookup(quotes)
    summaries: list[StoreSummary] = []

    for store in sorted(quotes.keys()):
        available_item_count = 0
        subtotal = 0.0
        delivery_fee = 0.0
        min_order = 0.0

        for item in purchasable_items:
            quote = quote_lookup.get((store, _item_key(item)))
            if quote is None:
                continue
            delivery_fee = max(delivery_fee, quote.delivery_fee)
            min_order = max(min_order, quote.min_order)
            if not quote.in_stock:
                continue
            available_item_count += 1
            subtotal += quote.price

        item_count = len(purchasable_items)
        total = subtotal + (delivery_fee if available_item_count else 0.0)
        summaries.append(
            StoreSummary(
                store=store,
                item_count=item_count,
                available_item_count=available_item_count,
                subtotal=round(subtotal, 2),
                delivery_fee=round(delivery_fee if available_item_count else 0.0, 2),
                total=round(total, 2),
                min_order=round(min_order, 2),
                all_items_available=item_count > 0 and available_item_count == item_count,
                meets_min_order=(subtotal >= min_order) if available_item_count else True,
            )
        )

    return summaries


def build_split_selection(items: Iterable[GroceryItem]) -> PricingSelection:
    item_store_map: Dict[str, str] = {}
    channels_by_store: Dict[str, str] = {}

    for item in items:
        if item.already_have or item.shopping_quantity <= 0 or item.best_store is None:
            continue
        item_store_map[_item_key(item)] = item.best_store
        channels_by_store.setdefault(item.best_store, "online")

    return PricingSelection(item_store_map=item_store_map, channels_by_store=channels_by_store)


def build_single_store_selection(
    items: Iterable[GroceryItem],
    store: str,
) -> PricingSelection:
    item_store_map = {
        _item_key(item): store
        for item in items
        if not item.already_have and item.shopping_quantity > 0
    }
    channels_by_store = {store: "online"} if item_store_map else {}
    return PricingSelection(item_store_map=item_store_map, channels_by_store=channels_by_store)


def build_purchase_orders(
    items: Iterable[GroceryItem],
    quotes: Mapping[str, Sequence[StoreQuote]],
    selection: PricingSelection,
) -> list[PurchaseOrder]:
    quote_lookup = _quote_lookup(quotes)
    grouped_items: dict[str, list[PurchaseOrderItem]] = defaultdict(list)

    for item in items:
        if item.already_have or item.shopping_quantity <= 0:
            continue

        store = selection.item_store_map.get(_item_key(item))
        if store is None:
            continue

        quote = quote_lookup.get((store, _item_key(item)))
        if quote is None or not quote.in_stock:
            continue

        grouped_items[store].append(
            PurchaseOrderItem(
                name=item.name,
                quantity=item.shopping_quantity,
                unit=item.unit,
                category=item.category,
                source_recipe_ids=item.source_recipe_ids,
                price=round(quote.price, 2),
                unit_price=round(quote.unit_price, 2),
            )
        )

    orders: list[PurchaseOrder] = []
    for store in sorted(grouped_items.keys()):
        store_items = grouped_items[store]
        channel = selection.channels_by_store.get(store, "online")
        subtotal = round(sum(item.price for item in store_items), 2)
        delivery_fee = 0.0
        if channel != "in_store":
            for quote in quotes.get(store, []):
                if quote.in_stock and any(order_item.name == quote.item_name for order_item in store_items):
                    delivery_fee = max(delivery_fee, quote.delivery_fee)

        orders.append(
            PurchaseOrder(
                store=store,
                items=store_items,
                subtotal=subtotal,
                delivery_fee=round(delivery_fee, 2),
                total_cost=round(subtotal + delivery_fee, 2),
                channel=channel,  # type: ignore[arg-type]
                status="pending",
            )
        )

    return orders


def total_order_cost(orders: Sequence[PurchaseOrder]) -> float:
    return round(sum(order.total_cost for order in orders), 2)


def missing_priced_items(items: Iterable[GroceryItem], orders: Sequence[PurchaseOrder]) -> list[str]:
    required = Counter(
        _item_key(item)
        for item in items
        if not item.already_have and item.shopping_quantity > 0
    )
    covered = Counter(
        _item_key_from_order_item(order_item)
        for order in orders
        for order_item in order.items
    )
    missing: list[str] = []
    for key, required_count in required.items():
        for _ in range(required_count - covered.get(key, 0)):
            missing.append(key)
    return sorted(missing)


def _quote_lookup(quotes: Mapping[str, Sequence[StoreQuote]]) -> dict[tuple[str, str], StoreQuote]:
    lookup: dict[tuple[str, str], StoreQuote] = {}
    for store, store_quotes in quotes.items():
        for quote in store_quotes:
            lookup[(store, _item_key_from_quote(quote))] = quote
    return lookup


def _quotes_for_item(
    quotes: Mapping[str, Sequence[StoreQuote]],
    item: GroceryItem,
) -> list[StoreQuote]:
    item_key = _item_key(item)
    return [
        quote
        for store_quotes in quotes.values()
        for quote in store_quotes
        if _item_key_from_quote(quote) == item_key
    ]


def _item_key(item: GroceryItem) -> str:
    quantity = round(item.shopping_quantity if item.shopping_quantity > 0 else item.quantity, 2)
    return "{name}|{unit}|{quantity}".format(
        name=item.name.lower().strip(),
        unit=(item.unit or "").lower(),
        quantity=quantity,
    )


def _item_key_from_quote(quote: StoreQuote) -> str:
    return "{name}|{unit}|{quantity}".format(
        name=quote.item_name.lower().strip(),
        unit=(quote.requested_unit or "").lower(),
        quantity=round(quote.requested_quantity, 2),
    )


def _item_key_from_order_item(item: PurchaseOrderItem) -> str:
    return "{name}|{unit}|{quantity}".format(
        name=item.name.lower().strip(),
        unit=(item.unit or "").lower(),
        quantity=round(item.quantity, 2),
    )
