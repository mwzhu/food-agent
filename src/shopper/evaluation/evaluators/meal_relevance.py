from __future__ import annotations

from typing import Any, Dict, List

from shopper.schemas import MealSlot


class MealRelevanceEvaluator:
    def evaluate(self, case: Dict[str, Any], meals: List[MealSlot], recipe_lookup) -> Dict[str, Any]:
        issues: List[str] = []

        if len(meals) < 28:
            issues.append("Expected at least 28 planned meal slots including snacks.")

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

        prep_cap = case.get("expected", {}).get("max_weeknight_dinner_min")
        if prep_cap is not None:
            for meal in meals:
                if meal.meal_type == "dinner" and meal.day in {"monday", "tuesday", "wednesday", "thursday", "friday"}:
                    if meal.prep_time_min > prep_cap:
                        issues.append(
                            "Weeknight dinner {recipe} exceeded the prep cap.".format(
                                recipe=meal.recipe_name
                            )
                        )

        return {"passed": not issues, "issues": sorted(set(issues))}
