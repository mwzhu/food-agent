from __future__ import annotations

import asyncio

from shopper.config import Settings
from shopper.memory.context_assembler import ContextAssembler


class DummyMemoryStore:
    pass


def test_context_assembler_trims_payload_to_budget():
    assembler = ContextAssembler(
        memory_store=DummyMemoryStore(),
        settings=Settings(
            SHOPPER_APP_ENV="test",
            SHOPPER_CONTEXT_TOKENIZER="cl100k_base",
            LANGSMITH_TRACING=False,
        ),
    )
    state = {
        "user_profile": {
            "age": 29,
            "sex": "female",
            "activity_level": "lightly_active",
            "goal": "maintain",
            "budget_weekly": 130,
            "household_size": 1,
            "cooking_skill": "intermediate",
            "dietary_restrictions": ["vegetarian"],
            "allergies": ["peanut"],
            "schedule_json": {f"day_{index}": "very detailed schedule " * 20 for index in range(12)},
        },
        "nutrition_plan": {
            "tdee": 2400,
            "daily_calories": 2200,
            "protein_g": 160,
            "carbs_g": 220,
            "fat_g": 70,
            "fiber_g": 30,
            "goal": "maintain",
            "applied_restrictions": ["vegetarian"],
        },
        "user_preferences_learned": {
            "preferred_cuisines": ["thai", "mediterranean", "mexican", "japanese", "indian", "korean", "greek"],
            "avoided_ingredients": [f"ingredient-{index}" for index in range(30)],
            "preferred_meal_types": ["breakfast", "lunch", "dinner", "snack"],
            "notes": ["long note " * 40 for _ in range(10)],
        },
        "retrieved_memories": [
            {
                "memory_id": f"memory-{index}",
                "user_id": "user-1",
                "category": "meal_feedback",
                "content": "memory item " * 300,
                "metadata": {},
            }
            for index in range(200)
        ],
    }

    context = asyncio.run(assembler.build_context("meal_selector", state))

    assert context.budget.tokens_used <= context.budget.token_budget
    assert context.budget.fields_dropped
    assert len(context.payload.get("top_k_memories", [])) < len(state["retrieved_memories"])


def test_context_assembler_includes_failed_plan_and_critic_feedback_for_replans():
    assembler = ContextAssembler(
        memory_store=DummyMemoryStore(),
        settings=Settings(
            SHOPPER_APP_ENV="test",
            SHOPPER_CONTEXT_TOKENIZER="cl100k_base",
            LANGSMITH_TRACING=False,
        ),
    )
    state = {
        "user_profile": {
            "age": 29,
            "sex": "female",
            "activity_level": "lightly_active",
            "goal": "maintain",
            "budget_weekly": 130,
            "household_size": 1,
            "cooking_skill": "intermediate",
            "dietary_restrictions": ["vegetarian"],
            "allergies": ["peanut"],
            "schedule_json": {"weekday": "quick dinner"},
        },
        "nutrition_plan": {
            "tdee": 2400,
            "daily_calories": 2200,
            "protein_g": 160,
            "carbs_g": 220,
            "fat_g": 70,
            "fiber_g": 30,
            "goal": "maintain",
            "applied_restrictions": ["vegetarian"],
        },
        "user_preferences_learned": {
            "preferred_cuisines": ["thai"],
            "avoided_ingredients": ["peanut"],
            "preferred_meal_types": ["dinner"],
            "notes": ["prefers high-protein meals"],
        },
        "retrieved_memories": [],
        "selected_meals": [
            {
                "day": "monday",
                "meal_type": "dinner",
                "recipe_id": "repeat-dinner",
                "recipe_name": "Repeat Dinner",
                "cuisine": "thai",
                "prep_time_min": 20,
                "serving_multiplier": 1.0,
                "calories": 540,
                "protein_g": 34,
                "carbs_g": 48,
                "fat_g": 16,
                "tags": ["high-protein"],
                "macro_fit_score": 0.61,
                "recipe": None,
            }
        ],
        "critic_verdict": {
            "passed": False,
            "issues": ["Meal slot repeat-dinner drifted too far from the recipe source nutrition."],
            "warnings": ["Cuisine repeat detected for thai around monday."],
            "repair_instructions": ["Choose a dinner with tighter nutrition grounding."],
        },
        "replan_count": 1,
    }

    context = asyncio.run(assembler.build_context("meal_selector", state))

    assert context.payload["previous_failed_plan"][0]["recipe_id"] == "repeat-dinner"
    assert context.payload["critic_feedback"]["repair_instructions"] == [
        "Choose a dinner with tighter nutrition grounding."
    ]
    assert context.payload["replan_attempt"] == 1


def test_context_assembler_builds_shopping_critic_context_with_fridge_and_traceability():
    assembler = ContextAssembler(
        memory_store=DummyMemoryStore(),
        settings=Settings(
            SHOPPER_APP_ENV="test",
            SHOPPER_CONTEXT_TOKENIZER="cl100k_base",
            LANGSMITH_TRACING=False,
        ),
    )
    state = {
        "user_profile": {
            "age": 29,
            "sex": "female",
            "activity_level": "lightly_active",
            "goal": "maintain",
            "budget_weekly": 130,
            "household_size": 2,
            "cooking_skill": "intermediate",
            "dietary_restrictions": [],
            "allergies": [],
            "schedule_json": {"weekday": "quick dinner"},
        },
        "selected_meals": [
            {
                "day": "monday",
                "meal_type": "dinner",
                "recipe_id": "sheet-pan-dinner",
                "recipe_name": "Sheet Pan Dinner",
                "cuisine": "american",
                "prep_time_min": 25,
                "serving_multiplier": 1.0,
                "calories": 520,
                "protein_g": 42,
                "carbs_g": 48,
                "fat_g": 12,
                "tags": ["high-protein"],
                "macro_fit_score": 0.91,
                "recipe": None,
            }
        ],
        "grocery_list": [
            {
                "name": "chicken breast",
                "quantity": 5.0,
                "unit": "oz",
                "category": "meat",
                "already_have": False,
                "shopping_quantity": 5.0,
                "quantity_in_fridge": 0.0,
                "source_recipe_ids": ["sheet-pan-dinner"],
            }
        ],
        "fridge_inventory": [
            {
                "item_id": 1,
                "user_id": "user-1",
                "name": "spinach",
                "quantity": 2.0,
                "unit": "cup",
                "category": "produce",
                "expiry_date": None,
            }
        ],
    }

    context = asyncio.run(assembler.build_context("shopping_critic", state))

    assert context.payload["grocery_list"][0]["source_recipe_ids"] == ["sheet-pan-dinner"]
    assert context.payload["fridge_inventory"][0]["name"] == "spinach"
