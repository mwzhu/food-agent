from __future__ import annotations

import asyncio

from shopper.agents.nodes import SubstitutionNode


class FakeStructuredModel:
    def __init__(self, schema, response, calls):
        self.schema = schema
        self.response = response
        self.calls = calls

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return self.schema.model_validate(self.response)


class FakeChatModel:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def with_structured_output(self, schema):
        return FakeStructuredModel(schema=schema, response=self.response, calls=self.calls)


def test_substitution_node_increments_replan_and_blocks_flagged_recipe():
    node = SubstitutionNode()
    state = {
        "run_id": "test-run",
        "critic_verdict": {
            "passed": False,
            "issues": ["Recipe dinner-bad-choice is missing from the retrieval store."],
            "warnings": ["Cuisine repeat detected for italian around thursday."],
            "repair_instructions": ["Select only recipes that resolve from the recipe store."],
        },
        "selected_meals": [],
        "repair_instructions": [],
        "replan_count": 0,
        "blocked_recipe_ids": [],
        "avoid_cuisines": [],
    }

    result = asyncio.run(node(state))

    assert result["replan_count"] == 1
    assert "dinner-bad-choice" in result["blocked_recipe_ids"]
    assert "italian" in result["avoid_cuisines"]


def test_substitution_node_merges_llm_constraints():
    chat_model = FakeChatModel(
        {
            "blocked_recipe_ids": ["lunch-repeat-meal"],
            "avoid_cuisines": ["thai"],
            "repair_instructions": ["Replace the repeated lunch with a distinct cuisine."],
            "rationale": "The lunch slot is overly repetitive.",
        }
    )
    node = SubstitutionNode(chat_model=chat_model)
    state = {
        "run_id": "test-run",
        "critic_verdict": {
            "passed": False,
            "issues": [],
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
                "macro_fit_score": 0.92,
                "recipe": None,
            }
        ],
        "repair_instructions": [],
        "replan_count": 0,
        "blocked_recipe_ids": [],
        "avoid_cuisines": [],
    }

    result = asyncio.run(node(state))

    assert "lunch-repeat-meal" in result["blocked_recipe_ids"]
    assert "thai" in result["avoid_cuisines"]
    assert "Replace the repeated lunch with a distinct cuisine." in result["repair_instructions"]
    assert chat_model.calls
