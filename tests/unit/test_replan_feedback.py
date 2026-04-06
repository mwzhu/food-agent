from __future__ import annotations

from shopper.agents.replan import derive_replan_feedback


def test_replan_feedback_increments_counter_and_derives_constraints():
    state = {
        "critic_verdict": {
            "passed": False,
            "issues": ["Recipe dinner-bad-choice is missing from the retrieval store."],
            "warnings": ["Too much Italian back-to-back in this plan."],
            "repair_instructions": ["Select only recipes that resolve from the recipe store."],
            "findings": [
                {
                    "code": "P_GROUNDEDNESS",
                    "severity": "issue",
                    "message": "Recipe dinner-bad-choice is missing from the retrieval store.",
                },
                {
                    "code": "P_VARIETY",
                    "severity": "warning",
                    "message": "Too much Italian back-to-back in this plan.",
                },
            ],
        },
        "selected_meals": [
            {
                "day": "monday",
                "meal_type": "dinner",
                "recipe_id": "dinner-bad-choice",
                "recipe_name": "Bad Dinner",
                "cuisine": "italian",
                "prep_time_min": 25,
                "serving_multiplier": 1.0,
                "calories": 620,
                "protein_g": 34,
                "carbs_g": 58,
                "fat_g": 22,
                "tags": [],
                "macro_fit_score": 0.44,
                "recipe": None,
            },
            {
                "day": "tuesday",
                "meal_type": "lunch",
                "recipe_id": "lunch-repeat",
                "recipe_name": "Repeat Lunch",
                "cuisine": "italian",
                "prep_time_min": 20,
                "serving_multiplier": 1.0,
                "calories": 540,
                "protein_g": 31,
                "carbs_g": 47,
                "fat_g": 19,
                "tags": [],
                "macro_fit_score": 0.81,
                "recipe": None,
            },
        ],
        "repair_instructions": [],
        "replan_count": 0,
        "blocked_recipe_ids": [],
        "avoid_cuisines": [],
    }

    result = derive_replan_feedback(state)

    assert result["replan_count"] == 1
    assert "dinner-bad-choice" in result["blocked_recipe_ids"]
    assert "italian" in result["avoid_cuisines"]
    assert "Select only recipes that resolve from the recipe store." in result["repair_instructions"]
    assert result["issue_finding_codes"] == ["P_GROUNDEDNESS"]


def test_replan_feedback_does_not_block_generic_hyphenated_issue_text():
    state = {
        "critic_verdict": {
            "passed": False,
            "issues": ["High-protein meals are under-represented across the week."],
            "warnings": [],
            "repair_instructions": [],
        },
        "selected_meals": [
            {
                "day": "monday",
                "meal_type": "lunch",
                "recipe_id": "actual-meal-id",
                "recipe_name": "Actual Meal",
                "cuisine": "american",
                "prep_time_min": 15,
                "serving_multiplier": 1.0,
                "calories": 500,
                "protein_g": 30,
                "carbs_g": 40,
                "fat_g": 18,
                "tags": [],
                "macro_fit_score": 0.42,
                "recipe": None,
            }
        ],
        "repair_instructions": [],
        "replan_count": 0,
        "blocked_recipe_ids": [],
        "avoid_cuisines": [],
    }

    result = derive_replan_feedback(state)

    assert "high-protein" not in result["blocked_recipe_ids"]
    assert "under-represented" not in result["blocked_recipe_ids"]
    assert result["blocked_recipe_ids"] == ["actual-meal-id"]


def test_replan_feedback_uses_failed_plan_context_when_no_recipe_is_called_out():
    state = {
        "critic_verdict": {
            "passed": False,
            "issues": ["Nutrition values drifted too far from the recipe source nutrition."],
            "warnings": [],
            "repair_instructions": [],
        },
        "selected_meals": [
            {
                "day": "monday",
                "meal_type": "lunch",
                "recipe_id": "lunch-repeat-meal",
                "recipe_name": "Repeated Lunch",
                "cuisine": "thai",
                "prep_time_min": 15,
                "serving_multiplier": 1.0,
                "calories": 500,
                "protein_g": 30,
                "carbs_g": 40,
                "fat_g": 18,
                "tags": [],
                "macro_fit_score": 0.42,
                "recipe": None,
            }
        ],
        "repair_instructions": [],
        "replan_count": 0,
        "blocked_recipe_ids": [],
        "avoid_cuisines": [],
    }

    result = derive_replan_feedback(state)

    assert result["blocked_recipe_ids"] == ["lunch-repeat-meal"]
    assert "Use the previous failed meal plan as context and address the critic feedback directly." in result["repair_instructions"]


def test_replan_feedback_does_not_arbitrarily_block_meals_for_budget_only_failures():
    state = {
        "critic_verdict": {
            "passed": False,
            "issues": ["Optimized purchase orders exceed the weekly budget by $18.00."],
            "warnings": [],
            "repair_instructions": ["Choose cheaper meals and ingredients so the resulting basket fits within the weekly budget."],
            "findings": [
                {
                    "code": "P_BUDGET",
                    "severity": "issue",
                    "message": "Optimized purchase orders exceed the weekly budget by $18.00.",
                }
            ],
        },
        "selected_meals": [
            {
                "day": "monday",
                "meal_type": "dinner",
                "recipe_id": "expensive-dinner",
                "recipe_name": "Expensive Dinner",
                "cuisine": "french",
                "prep_time_min": 30,
                "serving_multiplier": 1.0,
                "calories": 650,
                "protein_g": 38,
                "carbs_g": 42,
                "fat_g": 28,
                "tags": [],
                "macro_fit_score": 0.88,
                "recipe": None,
            }
        ],
        "repair_instructions": [],
        "replan_count": 0,
        "blocked_recipe_ids": [],
        "avoid_cuisines": [],
        "replan_reason": "The cheapest complete basket still lands 18.00 over the weekly budget.",
    }

    result = derive_replan_feedback(state)

    assert result["blocked_recipe_ids"] == []
    assert any("fulfillment failure" in instruction for instruction in result["repair_instructions"])
    assert result["issue_finding_codes"] == ["P_BUDGET"]
