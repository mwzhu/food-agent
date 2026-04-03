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
            expected_protein = int(round(recipe.protein_g * meal.serving_multiplier))
            expected_carbs = int(round(recipe.carbs_g * meal.serving_multiplier))
            expected_fat = int(round(recipe.fat_g * meal.serving_multiplier))
            if abs(meal.calories - expected_calories) > 15:
                issues.append("Calories for {recipe_id} drifted from the source recipe.".format(recipe_id=meal.recipe_id))
            if abs(meal.protein_g - expected_protein) > 4:
                issues.append("Protein for {recipe_id} drifted from the source recipe.".format(recipe_id=meal.recipe_id))
            if abs(meal.carbs_g - expected_carbs) > 4:
                issues.append("Carbs for {recipe_id} drifted from the source recipe.".format(recipe_id=meal.recipe_id))
            if abs(meal.fat_g - expected_fat) > 4:
                issues.append("Fat for {recipe_id} drifted from the source recipe.".format(recipe_id=meal.recipe_id))

        return {"passed": not issues, "issues": sorted(set(issues))}
