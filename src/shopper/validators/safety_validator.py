from __future__ import annotations

from typing import Dict, Iterable, List, Set

from shopper.schemas import MealSlot


ALLERGEN_ALIASES: Dict[str, Set[str]] = {
    "peanut": {"peanut", "peanut oil", "groundnut"},
    "nut": {"peanut", "peanut oil", "almond", "cashew", "walnut", "pecan", "pistachio", "hazelnut"},
    "tree_nut": {"almond", "cashew", "walnut", "pecan", "pistachio", "hazelnut"},
    "dairy": {"milk", "butter", "cream", "yogurt", "cheese", "cottage cheese", "greek yogurt"},
    "egg": {"egg", "eggs"},
    "soy": {"soy", "soy sauce", "tofu", "edamame", "miso"},
    "fish": {"salmon", "tuna", "cod", "fish"},
    "shellfish": {"shrimp", "crab", "lobster", "shellfish"},
    "gluten": {"wheat", "flour", "bread", "tortilla", "orzo", "soba", "granola"},
}


def validate_meal_plan_safety(meals: Iterable[MealSlot], allergies: List[str]) -> List[str]:
    issues: List[str] = []
    for allergy in allergies:
        aliases = set(expand_allergy_terms([allergy]))
        for meal in meals:
            recipe = meal.recipe
            if recipe is None:
                continue
            ingredient_names = {ingredient.name.lower() for ingredient in recipe.ingredients}
            if any(alias in ingredient_names or any(alias in name for name in ingredient_names) for alias in aliases):
                issues.append(
                    "Allergen '{allergy}' detected in {meal} via recipe {recipe_id}.".format(
                        allergy=allergy,
                        meal=meal.recipe_name,
                        recipe_id=meal.recipe_id,
                    )
                )
    return sorted(set(issues))


def expand_allergy_terms(allergies: List[str]) -> List[str]:
    expanded: Set[str] = set()
    for allergy in allergies:
        normalized = allergy.lower().replace(" ", "_")
        expanded.add(allergy.lower())
        expanded.update(ALLERGEN_ALIASES.get(normalized, {allergy.lower()}))
    return sorted(expanded)
