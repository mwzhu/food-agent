from __future__ import annotations

import json
from typing import Any, Dict, Literal, Mapping, Optional

from shopper.config import Settings, get_settings
from shopper.memory.store import MemoryStore
from shopper.memory.types import AssembledContext, ContextBudget, EpisodicMemory
from shopper.schemas import CriticVerdict, FridgeItemSnapshot, GroceryItem, MealSlot, NutritionPlan, PreferenceSummary


NodeName = Literal[
    "load_memory",
    "nutrition_planner",
    "meal_selector",
    "critic",
    "planning_critic",
    "shopping_critic",
]


class ContextAssembler:
    def __init__(self, memory_store: MemoryStore, settings: Optional[Settings] = None) -> None:
        self.memory_store = memory_store
        self.settings = settings if settings is not None else get_settings()
        self._tokenizer = self._load_tokenizer()

    async def build_context(
        self,
        node_name: NodeName,
        state: Mapping[str, Any],
    ) -> AssembledContext:
        profile = state["user_profile"]

        if node_name == "load_memory":
            payload = {
                "user_profile_summary": self._profile_summary(profile),
                "schedule": self._compact_schedule(profile["schedule_json"]),
                "goal": profile["goal"],
            }
            memories: list[EpisodicMemory] = []
            token_budget = 1200
        elif node_name == "nutrition_planner":
            payload = {
                "user_profile_summary": self._profile_summary(profile),
                "dietary_restrictions": profile["dietary_restrictions"],
                "allergies": profile["allergies"],
                "schedule": self._compact_schedule(profile["schedule_json"]),
            }
            memories = []
            token_budget = 1400
        elif node_name == "meal_selector":
            nutrition_plan = NutritionPlan.model_validate(state["nutrition_plan"])
            preferences = PreferenceSummary.model_validate(state["user_preferences_learned"])
            memories = [EpisodicMemory.model_validate(memory) for memory in state["retrieved_memories"]]
            payload = {
                "user_profile_summary": self._profile_summary(profile),
                "nutrition_plan": self._compact_nutrition_plan(nutrition_plan),
                "schedule": self._compact_schedule(profile["schedule_json"]),
                "preference_summary": self._compact_preference_summary(preferences),
                "top_k_memories": [self._trim_string(memory.content, limit=240) for memory in memories],
            }
            prior_meals = [MealSlot.model_validate(meal) for meal in state.get("selected_meals", [])]
            critic_verdict_payload = state.get("critic_verdict")
            if prior_meals and critic_verdict_payload is not None:
                critic_verdict = CriticVerdict.model_validate(critic_verdict_payload)
                payload["previous_failed_plan"] = self._compact_meals(prior_meals)
                payload["critic_feedback"] = {
                    "issues": critic_verdict.issues,
                    "warnings": critic_verdict.warnings,
                    "repair_instructions": critic_verdict.repair_instructions,
                }
                payload["replan_attempt"] = state.get("replan_count", 0)
            token_budget = 3200
        elif node_name in {"critic", "planning_critic"}:
            nutrition_plan = NutritionPlan.model_validate(state["nutrition_plan"])
            meals = [MealSlot.model_validate(meal) for meal in state["selected_meals"]]
            memories = []
            payload = {
                "user_profile_summary": self._profile_summary(profile),
                "nutrition_plan": self._compact_nutrition_plan(nutrition_plan),
                "schedule": self._compact_schedule(profile["schedule_json"]),
                "selected_meals": self._compact_meals(meals),
                "allergies": profile["allergies"],
                "dietary_restrictions": profile["dietary_restrictions"],
            }
            token_budget = 2200
        elif node_name == "shopping_critic":
            meals = [MealSlot.model_validate(meal) for meal in state["selected_meals"]]
            memories = []
            payload = {
                "user_profile_summary": self._profile_summary(profile),
                "selected_meals": self._compact_meals(meals),
            }
            if state.get("grocery_list"):
                grocery_list = [GroceryItem.model_validate(item) for item in state["grocery_list"]]
                payload["grocery_list"] = [
                    {
                        "name": item.name,
                        "quantity": item.quantity,
                        "shopping_quantity": item.shopping_quantity,
                        "unit": item.unit,
                        "category": item.category,
                        "already_have": item.already_have,
                        "quantity_in_fridge": item.quantity_in_fridge,
                        "source_recipe_ids": item.source_recipe_ids,
                    }
                    for item in grocery_list
                ]
            if state.get("fridge_inventory"):
                fridge_inventory = [FridgeItemSnapshot.model_validate(item) for item in state["fridge_inventory"]]
                payload["fridge_inventory"] = self._compact_fridge_inventory(fridge_inventory)
            token_budget = 2200
        else:
            assert False, node_name

        payload, memories, dropped_fields = self._trim_to_budget(payload, memories, token_budget)
        budget = ContextBudget(
            token_budget=token_budget,
            tokens_used=self._estimate_tokens(payload),
            fields_included=list(payload.keys()),
            fields_dropped=dropped_fields,
        )
        return AssembledContext(node_name=node_name, payload=payload, retrieved_memories=memories, budget=budget)

    def _profile_summary(self, user_profile: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "age": user_profile["age"],
            "sex": user_profile["sex"],
            "activity_level": user_profile["activity_level"],
            "goal": user_profile["goal"],
            "budget_weekly": user_profile["budget_weekly"],
            "household_size": user_profile["household_size"],
            "cooking_skill": user_profile["cooking_skill"],
        }

    def _compact_schedule(self, schedule: Mapping[str, Any]) -> Dict[str, str]:
        return {str(key): self._trim_string(str(value), limit=80) for key, value in schedule.items()}

    def _compact_nutrition_plan(self, plan: NutritionPlan) -> Dict[str, Any]:
        return {
            "daily_calories": plan.daily_calories,
            "protein_g": plan.protein_g,
            "carbs_g": plan.carbs_g,
            "fat_g": plan.fat_g,
            "fiber_g": plan.fiber_g,
            "goal": plan.goal,
            "applied_restrictions": plan.applied_restrictions,
        }

    def _compact_preference_summary(self, summary: PreferenceSummary) -> Dict[str, Any]:
        return {
            "preferred_cuisines": summary.preferred_cuisines[:6],
            "avoided_ingredients": summary.avoided_ingredients[:12],
            "preferred_meal_types": summary.preferred_meal_types[:8],
            "notes": [self._trim_string(note, limit=120) for note in summary.notes[:6]],
        }

    def _compact_meals(self, meals: list[MealSlot]) -> list[Dict[str, Any]]:
        return [
            {
                "day": meal.day,
                "meal_type": meal.meal_type,
                "recipe_id": meal.recipe_id,
                "recipe_name": meal.recipe_name,
                "cuisine": meal.cuisine,
                "prep_time_min": meal.prep_time_min,
                "serving_multiplier": meal.serving_multiplier,
                "calories": meal.calories,
                "protein_g": meal.protein_g,
                "carbs_g": meal.carbs_g,
                "fat_g": meal.fat_g,
                "macro_fit_score": meal.macro_fit_score,
            }
            for meal in meals
        ]

    def _compact_fridge_inventory(self, fridge_inventory: list[FridgeItemSnapshot]) -> list[Dict[str, Any]]:
        return [
            {
                "name": item.name,
                "quantity": item.quantity,
                "unit": item.unit,
                "category": item.category,
                "expiry_date": item.expiry_date,
            }
            for item in fridge_inventory
        ]

    def _estimate_tokens(self, payload: Mapping[str, Any]) -> int:
        serialized = self._serialize_payload(payload)
        if not serialized:
            return 0
        if self._tokenizer is not None:
            return len(self._tokenizer.encode(serialized))
        return max(1, len(serialized) // 4)

    def _serialize_payload(self, payload: Mapping[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), default=str)

    def _trim_to_budget(
        self,
        payload: Dict[str, Any],
        memories: list,
        token_budget: int,
    ) -> tuple[Dict[str, Any], list, list[str]]:
        trimmed_payload = dict(payload)
        trimmed_memories = list(memories)
        dropped_fields: list[str] = []

        while self._estimate_tokens(trimmed_payload) > token_budget and trimmed_payload.get("top_k_memories"):
            current_memories = list(trimmed_payload["top_k_memories"])
            current_memories.pop()
            trimmed_payload["top_k_memories"] = current_memories
            if trimmed_memories:
                trimmed_memories.pop()
            if "top_k_memories" not in dropped_fields:
                dropped_fields.append("top_k_memories")

        while self._estimate_tokens(trimmed_payload) > token_budget and trimmed_payload.get("previous_failed_plan"):
            current_meals = list(trimmed_payload["previous_failed_plan"])
            current_meals.pop()
            trimmed_payload["previous_failed_plan"] = current_meals
            if "previous_failed_plan" not in dropped_fields:
                dropped_fields.append("previous_failed_plan")

        while self._estimate_tokens(trimmed_payload) > token_budget and trimmed_payload.get("selected_meals"):
            current_meals = list(trimmed_payload["selected_meals"])
            current_meals.pop()
            trimmed_payload["selected_meals"] = current_meals
            if "selected_meals" not in dropped_fields:
                dropped_fields.append("selected_meals")

        while self._estimate_tokens(trimmed_payload) > token_budget and trimmed_payload.get("grocery_list"):
            current_grocery_list = list(trimmed_payload["grocery_list"])
            current_grocery_list.pop()
            trimmed_payload["grocery_list"] = current_grocery_list
            if "grocery_list" not in dropped_fields:
                dropped_fields.append("grocery_list")

        while self._estimate_tokens(trimmed_payload) > token_budget and trimmed_payload.get("fridge_inventory"):
            current_fridge_inventory = list(trimmed_payload["fridge_inventory"])
            current_fridge_inventory.pop()
            trimmed_payload["fridge_inventory"] = current_fridge_inventory
            if "fridge_inventory" not in dropped_fields:
                dropped_fields.append("fridge_inventory")

        for field_name in ("preference_summary", "schedule", "dietary_restrictions", "allergies"):
            if self._estimate_tokens(trimmed_payload) <= token_budget:
                break
            if field_name in trimmed_payload:
                trimmed_payload.pop(field_name, None)
                if field_name not in dropped_fields:
                    dropped_fields.append(field_name)

        if self._estimate_tokens(trimmed_payload) > token_budget and "user_profile_summary" in trimmed_payload:
            trimmed_payload["user_profile_summary"] = {
                key: trimmed_payload["user_profile_summary"][key]
                for key in ("goal", "cooking_skill", "budget_weekly")
                if key in trimmed_payload["user_profile_summary"]
            }
            if "user_profile_summary" not in dropped_fields:
                dropped_fields.append("user_profile_summary")

        return trimmed_payload, trimmed_memories, dropped_fields

    def _load_tokenizer(self):
        try:
            import tiktoken
        except ImportError:
            return None

        try:
            return tiktoken.get_encoding(self.settings.context_tokenizer)
        except Exception:
            return None

    def _trim_string(self, value: str, limit: int) -> str:
        normalized = " ".join(value.split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: max(0, limit - 3)] + "..."
