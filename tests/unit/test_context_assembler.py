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
