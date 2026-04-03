from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Literal, Mapping

from shopper.schemas import MealSlot, NutritionPlan


DAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")
MacroAlignmentMode = Literal["eval", "critic_blockers", "critic_warnings"]


def validate_meal_plan_slot_coverage(meals: Iterable[MealSlot]) -> list[str]:
    issues: list[str] = []
    seen_slots: dict[tuple[str, str], int] = {}

    for meal in meals:
        slot = (meal.day, meal.meal_type)
        seen_slots[slot] = seen_slots.get(slot, 0) + 1

    for day in DAYS:
        for meal_type in MEAL_TYPES:
            slot = (day, meal_type)
            count = seen_slots.get(slot, 0)
            if count == 0:
                issues.append("Missing meal slot for {day} {meal_type}.".format(day=day, meal_type=meal_type))
            elif count > 1:
                issues.append("Duplicate meal slot for {day} {meal_type}.".format(day=day, meal_type=meal_type))

    return issues


def daily_macro_alignment(meals: Iterable[MealSlot]) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    )
    for meal in meals:
        day_totals = totals[meal.day]
        day_totals["calories"] += meal.calories
        day_totals["protein_g"] += meal.protein_g
        day_totals["carbs_g"] += meal.carbs_g
        day_totals["fat_g"] += meal.fat_g

    return {day: {metric: round(value, 2) for metric, value in metrics.items()} for day, metrics in totals.items()}


def validate_daily_macro_alignment(
    plan: NutritionPlan,
    meals: Iterable[MealSlot],
    mode: MacroAlignmentMode,
) -> list[str]:
    issues: list[str] = []
    daily_totals = daily_macro_alignment(meals)
    targets = {
        "calories": float(plan.daily_calories),
        "protein_g": float(plan.protein_g),
        "carbs_g": float(plan.carbs_g),
        "fat_g": float(plan.fat_g),
    }
    if mode == "eval":
        tolerance_by_metric = {
            "calories": 0.15,
            "protein_g": 0.25,
            "carbs_g": 0.30,
            "fat_g": 0.35,
        }
        selected_metrics = tuple(targets.keys())
    elif mode == "critic_blockers":
        tolerance_by_metric = {"calories": 0.28, "protein_g": 0.40}
        selected_metrics = ("calories", "protein_g")
    elif mode == "critic_warnings":
        tolerance_by_metric = {"carbs_g": 0.30, "fat_g": 0.35}
        selected_metrics = ("carbs_g", "fat_g")
    else:
        assert False, mode

    for day in DAYS:
        day_totals = daily_totals.get(day)
        if day_totals is None:
            continue
        for metric in selected_metrics:
            target = targets[metric]
            tolerance_pct = tolerance_by_metric[metric]
            actual = float(day_totals[metric])
            delta_pct = abs(actual - target) / max(target, 1.0)
            if delta_pct > tolerance_pct:
                issues.append(
                    "{day} {metric} missed the daily target by {delta_pct:.0%}.".format(
                        day=day.title(),
                        metric=metric.replace("_g", "").replace("_", " "),
                        delta_pct=delta_pct,
                    )
                )

    return issues


def validate_meal_plan_schedule_fit(meals: Iterable[MealSlot], schedule: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    for meal in meals:
        if meal.prep_time_min > prep_cap_for_day(schedule, meal.meal_type, meal.day):
            issues.append(
                "{day} {meal_type} {recipe} exceeded the prep cap.".format(
                    day=meal.day.title(),
                    meal_type=meal.meal_type,
                    recipe=meal.recipe_name,
                )
            )
    return issues


def prep_cap_for_day(schedule: Mapping[str, Any], meal_type: str, day: str) -> int:
    defaults = {"breakfast": 15, "lunch": 20, "dinner": 35, "snack": 10}
    if meal_type != "dinner":
        return defaults.get(meal_type, 20)

    normalized_schedule = {str(key).lower(): str(value).lower() for key, value in schedule.items()}
    matching_entries = [
        value
        for key, value in normalized_schedule.items()
        if day[:3] in key or day in key or "weeknight" in key or "weekday" in key
    ]
    if day in {"saturday", "sunday"}:
        matching_entries.extend(
            value
            for key, value in normalized_schedule.items()
            if "weekend" in key or "saturday" in key or "sunday" in key
        )

    for entry in matching_entries:
        digits = "".join(character for character in entry if character.isdigit())
        if digits:
            return max(15, int(digits))
        if "quick" in entry:
            return 25
        if "flex" in entry or "slow" in entry:
            return 45

    return defaults["dinner"]
