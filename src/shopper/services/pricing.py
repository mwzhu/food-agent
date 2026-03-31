from __future__ import annotations

from dataclasses import dataclass

from shopper.schemas import BasketPlan, BasketPlanItem, GroceryDemandItem, StoreQuote


STORE_MULTIPLIERS = {
    "walmart": 1.0,
    "mock_club": 0.92,
    "mock_organic": 1.18,
}


@dataclass
class QuoteAdapter:
    store: str

    async def quote_items(self, items: list[GroceryDemandItem]) -> list[StoreQuote]:
        quotes: list[StoreQuote] = []
        multiplier = STORE_MULTIPLIERS.get(self.store, 1.0)
        for item in items:
            if item.already_have:
                continue
            base_price = max(1.5, len(item.name) * 0.35)
            quotes.append(
                StoreQuote(
                    store=self.store,
                    item_name=item.name,
                    unit_price=round(base_price * multiplier, 2),
                    available=True,
                )
            )
        return quotes


def build_basket_plan(
    grocery_demand: list[GroceryDemandItem],
    quotes: list[StoreQuote],
    preferred_stores: list[str],
) -> BasketPlan:
    quote_map: dict[str, list[StoreQuote]] = {}
    for quote in quotes:
        quote_map.setdefault(quote.item_name, []).append(quote)
    basket_items: list[BasketPlanItem] = []
    for item in grocery_demand:
        if item.already_have:
            continue
        item_quotes = quote_map.get(item.name, [])
        if not item_quotes:
            continue
        item_quotes.sort(key=lambda quote: (quote.unit_price, preferred_stores.index(quote.store) if quote.store in preferred_stores else 99))
        best_quote = item_quotes[0]
        basket_items.append(
            BasketPlanItem(
                item_name=item.name,
                store=best_quote.store,
                quantity=item.quantity,
                unit=item.unit,
                estimated_cost=round(best_quote.unit_price * max(item.quantity, 1), 2),
                buy_online=True,
            )
        )
    estimated_total = round(sum(item.estimated_cost for item in basket_items), 2)
    return BasketPlan(
        items=basket_items,
        estimated_total=estimated_total,
        rationale="Basket favors lowest verified unit price while respecting preferred stores.",
    )

