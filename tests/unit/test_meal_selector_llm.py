from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from shopper.agents.nodes.meal_selector import MealSelectorNode
from shopper.schemas import RecipeIngredient, RecipeRecord


class FakeRecipeSearchTool:
    def __init__(self):
        self.calls = []

    async def search(self, query, filters=None, top_k=5, context=None):
        slot_index = len(self.calls)
        meal_type = filters["meal_type"]
        cuisine = "thai" if "thai" in query else "american"
        prep_time_min = {
            "breakfast": 12,
            "lunch": 18,
            "dinner": 20,
            "snack": 8,
        }[meal_type]
        self.calls.append({"query": query, "filters": filters, "context": context})
        return [
            {
                "recipe": _recipe(
                    recipe_id=f"{meal_type}-{slot_index}-{candidate_index}",
                    name=f"{meal_type.title()} Candidate {candidate_index}",
                    cuisine="thai" if candidate_index >= 3 else cuisine,
                    calories=520 - (candidate_index * 10),
                    protein_g=35 + candidate_index,
                    meal_type=meal_type,
                    prep_time_min=prep_time_min,
                ).model_dump(mode="json"),
                "rerank_score": round(0.98 - (candidate_index * 0.03), 2),
                "reasons": ["top rank" if candidate_index == 0 else "alternate fit"],
            }
            for candidate_index in range(6)
        ]


class FakeContextAssembler:
    async def build_context(self, node_name, state):
        return SimpleNamespace(
            payload={"preference_summary": state["user_preferences_learned"]},
            budget=SimpleNamespace(
                tokens_used=128,
                token_budget=3200,
                fields_included=["preference_summary"],
                fields_dropped=[],
            ),
            retrieved_memories=[],
        )


class FakeStructuredModel:
    def __init__(self, schema, response, calls):
        self.schema = schema
        self.response = response
        self.calls = calls

    async def ainvoke(self, messages):
        self.calls.append(messages)
        response = self.response(messages) if callable(self.response) else self.response
        return self.schema.model_validate(response)


class FakeChatModel:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def with_structured_output(self, schema):
        return FakeStructuredModel(schema=schema, response=self.response, calls=self.calls)


def _recipe(
    recipe_id: str,
    name: str,
    cuisine: str,
    calories: int,
    protein_g: int,
    meal_type: str = "lunch",
    prep_time_min: int = 20,
) -> RecipeRecord:
    return RecipeRecord(
        recipe_id=recipe_id,
        name=name,
        cuisine=cuisine,
        meal_types=[meal_type],
        ingredients=[RecipeIngredient(name="chicken breast"), RecipeIngredient(name="rice")],
        prep_time_min=prep_time_min,
        calories=calories,
        protein_g=protein_g,
        carbs_g=30,
        fat_g=12,
        tags=["high-protein"],
        instructions=["Cook and serve."],
        source_url=None,
    )


def _state():
    return {
        "run_id": "selector-run",
        "user_profile": {
            "age": 31,
            "weight_lbs": 175,
            "height_in": 70,
            "sex": "male",
            "activity_level": "moderately_active",
            "goal": "maintain",
            "dietary_restrictions": [],
            "allergies": [],
            "budget_weekly": 140,
            "household_size": 1,
            "cooking_skill": "intermediate",
            "schedule_json": {"weekdays": "quick"},
        },
        "nutrition_plan": {
            "tdee": 2400,
            "daily_calories": 2400,
            "protein_g": 180,
            "carbs_g": 220,
            "fat_g": 80,
            "fiber_g": 30,
            "goal": "maintain",
            "applied_restrictions": [],
            "notes": "",
        },
        "user_preferences_learned": {"preferred_cuisines": ["thai"], "avoided_ingredients": []},
        "repair_instructions": [],
        "blocked_recipe_ids": [],
        "avoid_cuisines": [],
        "retrieved_memories": [],
    }


def _weekly_response(messages):
    payload = json.loads(messages[-1].content)
    for slot in payload["meal_slots"]:
        assert len(slot["candidates"]) == 4
        for candidate in slot["candidates"]:
            assert "carbs_g" in candidate
            assert "fat_g" in candidate
            assert "projected_carbs_g" in candidate
            assert "projected_fat_g" in candidate
    return {
        "selections": [
            {
                "slot_id": slot["slot_id"],
                "recipe_id": slot["candidates"][3]["recipe_id"],
                "rationale": "Preferred cuisine improves week-level fit.",
            }
            for slot in payload["meal_slots"]
        ]
    }


def test_meal_selector_uses_one_llm_call_for_the_whole_week():
    recipe_search = FakeRecipeSearchTool()
    chat_model = FakeChatModel(_weekly_response)
    node = MealSelectorNode(
        context_assembler=FakeContextAssembler(),
        recipe_search=recipe_search,
        chat_model=chat_model,
    )
    state = _state()

    result = asyncio.run(node(state))

    assert len(recipe_search.calls) == 28
    assert len(chat_model.calls) == 1
    assert len(result["selected_meals"]) == 28
    assert all(meal["recipe_id"].endswith("-3") for meal in result["selected_meals"])


def test_meal_selector_falls_back_when_weekly_llm_response_is_incomplete():
    def incomplete_response(messages):
        weekly_response = _weekly_response(messages)
        weekly_response["selections"] = weekly_response["selections"][:-1]
        return weekly_response

    recipe_search = FakeRecipeSearchTool()
    chat_model = FakeChatModel(incomplete_response)
    node = MealSelectorNode(
        context_assembler=FakeContextAssembler(),
        recipe_search=recipe_search,
        chat_model=chat_model,
    )
    state = _state()

    result = asyncio.run(node(state))

    assert len(chat_model.calls) == 1
    assert len(result["selected_meals"]) == 28
    assert all(meal["recipe_id"].endswith("-0") for meal in result["selected_meals"])
