from __future__ import annotations

from typing import Any, Dict, List

from shopper.schemas import MealSlot


class GroundednessEvaluator:
    def evaluate(self, case: Dict[str, Any], meals: List[MealSlot], recipe_lookup) -> Dict[str, Any]:
        issues: List[str] = []
        for meal in meals:
            recipe = recipe_lookup(meal.recipe_id)
            if recipe is None:
                issues.append("Recipe {recipe_id} could not be resolved.".format(recipe_id=meal.recipe_id))
                continue

            expected_calories = int(round(recipe.calories * meal.serving_multiplier))
            if abs(meal.calories - expected_calories) > 15:
                issues.append("Calories for {recipe_id} drifted from the source recipe.".format(recipe_id=meal.recipe_id))

        return {"passed": not issues, "issues": sorted(set(issues))}
