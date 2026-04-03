from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from shopper.schemas import CriticVerdict, MealSlot


def derive_replan_feedback(state: Dict[str, Any]) -> Dict[str, Any]:
    verdict = CriticVerdict.model_validate(state["critic_verdict"])
    meals = [MealSlot.model_validate(item) for item in state.get("selected_meals", [])]

    blocked_recipe_ids = sorted(
        set(state.get("blocked_recipe_ids", []))
        | _blocked_recipe_ids(verdict, meals)
    )
    avoid_cuisines = sorted(
        set(state.get("avoid_cuisines", []))
        | _repeated_cuisines(meals)
    )
    repair_instructions = _dedupe(
        list(state.get("repair_instructions", []))
        + verdict.repair_instructions
        + _replan_guidance(meals)
    )

    return {
        "replan_count": state.get("replan_count", 0) + 1,
        "repair_instructions": repair_instructions,
        "blocked_recipe_ids": blocked_recipe_ids,
        "avoid_cuisines": avoid_cuisines,
    }


def _blocked_recipe_ids(verdict: CriticVerdict, meals: List[MealSlot]) -> Set[str]:
    known_recipe_ids = {meal.recipe_id.lower(): meal.recipe_id for meal in meals}
    blocked: Set[str] = set()
    for issue in verdict.issues:
        lowered_issue = issue.lower()
        for lowered_recipe_id, recipe_id in known_recipe_ids.items():
            if _mentions_recipe_id(lowered_issue, lowered_recipe_id):
                blocked.add(recipe_id)

    if not blocked and meals:
        blocked.add(min(meals, key=lambda meal: meal.macro_fit_score).recipe_id)

    return blocked


def _mentions_recipe_id(issue_text: str, recipe_id: str) -> bool:
    pattern = r"(?<![a-z0-9-]){recipe_id}(?![a-z0-9-])".format(recipe_id=re.escape(recipe_id))
    return re.search(pattern, issue_text) is not None


def _repeated_cuisines(meals: List[MealSlot]) -> Set[str]:
    cuisines: Set[str] = set()
    seen_by_day: Dict[str, List[str]] = {}
    for meal in meals:
        recent_cuisines: List[str] = []
        for day_cuisines in list(seen_by_day.values())[-2:]:
            recent_cuisines.extend(day_cuisines)
        if meal.cuisine and meal.cuisine in recent_cuisines:
            cuisines.add(meal.cuisine.lower())
        seen_by_day.setdefault(meal.day, []).append(meal.cuisine)
    return cuisines


def _replan_guidance(meals: List[MealSlot]) -> List[str]:
    instructions = ["Apply stricter novelty rules to avoid repeating recently rejected meals."]
    if meals:
        instructions.insert(0, "Use the previous failed meal plan as context and address the critic feedback directly.")
    return instructions


def _dedupe(values: List[str]) -> List[str]:
    return list(dict.fromkeys(value for value in values if value))
