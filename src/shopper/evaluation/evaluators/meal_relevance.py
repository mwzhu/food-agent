from __future__ import annotations

from typing import Any, Dict, List

from shopper.schemas import MealSlot
from shopper.validators import validate_meal_plan_schedule_fit, validate_meal_plan_slot_coverage


class MealRelevanceEvaluator:
    def evaluate(self, case: Dict[str, Any], meals: List[MealSlot], recipe_lookup) -> Dict[str, Any]:
        issues: List[str] = validate_meal_plan_slot_coverage(meals)

        recent_cuisines_by_day: Dict[str, List[str]] = {}
        for meal in meals:
            if recipe_lookup(meal.recipe_id) is None:
                issues.append("Recipe {recipe_id} was not grounded in the recipe store.".format(recipe_id=meal.recipe_id))

            recent_cuisines = []
            for cuisines in list(recent_cuisines_by_day.values())[-2:]:
                recent_cuisines.extend(cuisines)
            if meal.cuisine in recent_cuisines:
                issues.append(
                    "Cuisine {cuisine} repeated too tightly around {day}.".format(
                        cuisine=meal.cuisine,
                        day=meal.day,
                    )
                )
            recent_cuisines_by_day.setdefault(meal.day, []).append(meal.cuisine)

        issues.extend(validate_meal_plan_schedule_fit(meals, case["profile"].get("schedule_json", {})))

        return {"passed": not issues, "issues": sorted(set(issues))}
