from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from shopper.schemas import FridgeItemSnapshot, GroceryItem, InventoryCategory, MealSlot


VOLUME_TO_ML = {
    "tsp": 4.92892,
    "tbsp": 14.7868,
    "cup": 240.0,
    "ml": 1.0,
    "l": 1000.0,
}
WEIGHT_TO_G = {
    "g": 1.0,
    "kg": 1000.0,
    "oz": 28.3495,
    "lb": 453.592,
}
UNIT_ALIASES = {
    "cups": "cup",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "ounces": "oz",
    "ounce": "oz",
    "pounds": "lb",
    "pound": "lb",
    "grams": "g",
    "gram": "g",
    "kilograms": "kg",
    "kilogram": "kg",
    "milliliters": "ml",
    "milliliter": "ml",
    "liters": "l",
    "liter": "l",
    "cloves": "clove",
    "slices": "slice",
    "pieces": "piece",
}
CATEGORY_HINTS: dict[InventoryCategory, tuple[str, ...]] = {
    "produce": (
        "apple",
        "avocado",
        "banana",
        "basil",
        "berries",
        "berry",
        "blueberry",
        "broccoli",
        "carrot",
        "celery",
        "cilantro",
        "cucumber",
        "garlic",
        "ginger",
        "grape",
        "herb",
        "jalapeno",
        "kale",
        "lemon",
        "lettuce",
        "lime",
        "mango",
        "mushroom",
        "onion",
        "orange",
        "parsley",
        "peach",
        "pear",
        "pepper",
        "pineapple",
        "potato",
        "spinach",
        "squash",
        "strawberry",
        "tomato",
        "zucchini",
    ),
    "dairy": ("butter", "cheese", "cream", "egg", "milk", "parmesan", "yogurt"),
    "meat": (
        "bacon",
        "beef",
        "breast",
        "chicken",
        "cod",
        "fish",
        "ham",
        "pork",
        "salmon",
        "sausage",
        "shrimp",
        "steak",
        "tilapia",
        "tofu",
        "tuna",
        "turkey",
    ),
    "frozen": ("frozen",),
    "pantry": (),
}


@dataclass(frozen=True)
class RawIngredient:
    name: str
    quantity: float
    unit: Optional[str]
    recipe_id: str


@dataclass(frozen=True)
class AggregatedItem:
    name: str
    quantity: float
    unit: Optional[str]
    source_recipe_ids: tuple[str, ...]


def extract_ingredients(meals: Iterable[MealSlot]) -> list[RawIngredient]:
    ingredients: list[RawIngredient] = []
    for meal in meals:
        recipe = meal.recipe
        assert recipe is not None, meal.recipe_id
        for ingredient in recipe.ingredients:
            ingredients.append(
                RawIngredient(
                    name=ingredient.name,
                    quantity=round_quantity((ingredient.quantity or 1.0) * meal.serving_multiplier),
                    unit=normalize_unit(ingredient.unit),
                    recipe_id=recipe.recipe_id,
                )
            )
    return ingredients


def aggregate_quantities(ingredients: Iterable[RawIngredient]) -> list[AggregatedItem]:
    grouped_quantity: dict[tuple[str, Optional[str]], float] = {}
    grouped_recipe_ids: dict[tuple[str, Optional[str]], list[str]] = {}

    for ingredient in ingredients:
        canonical_name = canonicalize_name(ingredient.name)
        bucket_key, converted_quantity = aggregation_key(canonical_name, ingredient.quantity, ingredient.unit)
        grouped_quantity[bucket_key] = grouped_quantity.get(bucket_key, 0.0) + converted_quantity
        grouped_recipe_ids.setdefault(bucket_key, []).append(ingredient.recipe_id)

    aggregated: list[AggregatedItem] = []
    for (name, unit), quantity in grouped_quantity.items():
        display_unit, display_quantity = display_quantity_for_unit_group(
            total_quantity=quantity,
            base_unit=unit,
        )
        source_recipe_ids = tuple(dict.fromkeys(grouped_recipe_ids[(name, unit)]))
        aggregated.append(
            AggregatedItem(
                name=name,
                quantity=display_quantity,
                unit=display_unit,
                source_recipe_ids=source_recipe_ids,
            )
        )

    return sorted(aggregated, key=lambda item: (infer_category(item.name), item.name))


def diff_against_fridge(
    items: Iterable[AggregatedItem],
    fridge: Iterable[FridgeItemSnapshot],
) -> list[GroceryItem]:
    fridge_index = build_fridge_index(fridge)
    grocery_items: list[GroceryItem] = []

    for item in items:
        required_base, comparable = quantity_to_comparable(item.quantity, item.unit)
        available_base = fridge_index.get((canonicalize_name(item.name), comparable), 0.0)
        available_display = quantity_from_comparable(available_base, item.unit)
        shopping_display = quantity_from_comparable(max(0.0, required_base - available_base), item.unit)
        grocery_items.append(
            GroceryItem(
                name=item.name,
                quantity=round_quantity(item.quantity),
                unit=item.unit,
                category=infer_category(item.name),
                already_have=available_base + 1e-6 >= required_base,
                shopping_quantity=round_quantity(shopping_display),
                quantity_in_fridge=round_quantity(min(item.quantity, available_display)),
                source_recipe_ids=list(item.source_recipe_ids),
            )
        )

    return grocery_items


def categorize(items: Iterable[GroceryItem]) -> list[GroceryItem]:
    return [item.model_copy(update={"category": infer_category(item.name)}) for item in items]


def convert_quantity(quantity: float, from_unit: Optional[str], to_unit: Optional[str]) -> float:
    normalized_from = normalize_unit(from_unit)
    normalized_to = normalize_unit(to_unit)
    if normalized_from == normalized_to:
        return round_quantity(quantity)

    comparable_quantity, comparable_from = quantity_to_comparable(quantity, normalized_from)
    comparable_to = comparable_unit(normalized_to)
    assert comparable_from == comparable_to
    return round_quantity(quantity_from_comparable(comparable_quantity, normalized_to))


def canonicalize_name(name: str) -> str:
    return " ".join(name.lower().strip().replace("-", " ").split())


def normalize_unit(unit: Optional[str]) -> Optional[str]:
    if unit is None:
        return None
    normalized = unit.lower().strip()
    if not normalized:
        return None
    return UNIT_ALIASES.get(normalized, normalized)


def comparable_unit(unit: Optional[str]) -> Optional[str]:
    normalized = normalize_unit(unit)
    if normalized in VOLUME_TO_ML:
        return "ml"
    if normalized in WEIGHT_TO_G:
        return "g"
    return normalized


def quantity_to_comparable(quantity: float, unit: Optional[str]) -> tuple[float, Optional[str]]:
    normalized = normalize_unit(unit)
    if normalized in VOLUME_TO_ML:
        return quantity * VOLUME_TO_ML[normalized], "ml"
    if normalized in WEIGHT_TO_G:
        return quantity * WEIGHT_TO_G[normalized], "g"
    return quantity, normalized


def quantity_from_comparable(quantity: float, unit: Optional[str]) -> float:
    normalized = normalize_unit(unit)
    if normalized in VOLUME_TO_ML:
        return quantity / VOLUME_TO_ML[normalized]
    if normalized in WEIGHT_TO_G:
        return quantity / WEIGHT_TO_G[normalized]
    return quantity


def aggregation_key(name: str, quantity: float, unit: Optional[str]) -> tuple[tuple[str, Optional[str]], float]:
    comparable_quantity, base_unit = quantity_to_comparable(quantity, unit)
    if base_unit in {"ml", "g"}:
        return (name, base_unit), comparable_quantity
    return (name, normalize_unit(unit)), quantity


def display_quantity_for_unit_group(total_quantity: float, base_unit: Optional[str]) -> tuple[Optional[str], float]:
    if base_unit == "ml":
        for unit in ("cup", "tbsp", "tsp", "ml"):
            converted = total_quantity / VOLUME_TO_ML[unit]
            if converted >= 1 or unit == "ml":
                return unit, round_quantity(converted)
    if base_unit == "g":
        for unit in ("lb", "oz", "g"):
            converted = total_quantity / WEIGHT_TO_G[unit]
            if converted >= 1 or unit == "g":
                return unit, round_quantity(converted)
    return base_unit, round_quantity(total_quantity)


def build_fridge_index(fridge: Iterable[FridgeItemSnapshot]) -> dict[tuple[str, Optional[str]], float]:
    index: dict[tuple[str, Optional[str]], float] = {}
    for item in fridge:
        quantity, unit = quantity_to_comparable(item.quantity, item.unit)
        key = (canonicalize_name(item.name), unit)
        index[key] = index.get(key, 0.0) + quantity
    return index


def infer_category(name: str) -> InventoryCategory:
    normalized_name = canonicalize_name(name)
    for category in ("frozen", "meat", "dairy", "produce"):
        if any(hint in normalized_name for hint in CATEGORY_HINTS[category]):
            return category
    return "pantry"


def round_quantity(value: float) -> float:
    return round(value + 1e-9, 2)
