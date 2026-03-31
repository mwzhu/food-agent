from __future__ import annotations

from collections import defaultdict

from shopper.schemas import GroceryDemandItem, MealPlan, PantryItem


def derive_grocery_demand(meal_plan: MealPlan, pantry_snapshot: list[PantryItem]) -> list[GroceryDemandItem]:
    pantry_map = {item.name.lower(): item for item in pantry_snapshot}
    aggregated: dict[tuple[str, str, str], float] = defaultdict(float)
    for recipe in meal_plan.recipes:
        for ingredient in recipe.ingredients:
            key = (ingredient.name.lower(), ingredient.unit, ingredient.category or "general")
            aggregated[key] += ingredient.quantity
    demand: list[GroceryDemandItem] = []
    for (name, unit, category), quantity in aggregated.items():
        pantry_item = pantry_map.get(name)
        already_have = bool(pantry_item and pantry_item.quantity >= quantity)
        demand.append(
            GroceryDemandItem(
                name=name,
                quantity=quantity,
                unit=unit,
                category=category,
                already_have=already_have,
            )
        )
    demand.sort(key=lambda item: (item.already_have, item.category, item.name))
    return demand

