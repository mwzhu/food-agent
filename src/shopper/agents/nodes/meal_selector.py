from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from shopper.agents.events import emit_run_event
from shopper.agents.llm import invoke_structured
from shopper.agents.tools import RecipeSearchTool
from shopper.memory import ContextAssembler
from shopper.schemas import ContextMetadata, MealSlot, MealType, NutritionPlan, PreferenceSummary, RecipeRecord
from shopper.schemas.user import UserProfileBase
from shopper.validators import expand_allergy_terms


PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "meal_selector.md"
DAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
MEAL_TARGET_SPLITS = {
    "breakfast": 0.24,
    "lunch": 0.30,
    "dinner": 0.36,
    "snack": 0.10,
}
LLM_CANDIDATE_LIMIT = 4


class MealSelectionDecision(BaseModel):
    slot_id: str
    recipe_id: str
    rationale: str = Field(default="")


class WeeklyMealSelectionDecision(BaseModel):
    selections: list[MealSelectionDecision] = Field(default_factory=list)


@dataclass(frozen=True)
class MealRequest:
    day: str
    day_index: int
    meal_type: MealType
    max_prep_time: int
    query: str

    @property
    def slot_id(self) -> str:
        return "{day}:{meal_type}".format(day=self.day, meal_type=self.meal_type)


@dataclass(frozen=True)
class MealCandidateSet:
    slot: MealRequest
    candidates: list[Dict[str, Any]]
    candidate_recipes: list[RecipeRecord]


@dataclass(frozen=True)
class MealSelectorInputs:
    preferences: PreferenceSummary
    repair_instructions: list[str]
    blocked_recipe_ids: set[str]
    avoid_cuisines: set[str]


@dataclass
class MealSelectorNode:
    context_assembler: ContextAssembler
    recipe_search: RecipeSearchTool
    chat_model: Optional[Any] = None

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_entered",
            phase="planning",
            node_name="meal_selector",
            message="Searching the recipe corpus and composing a weekly meal plan.",
        )

        profile = UserProfileBase.model_validate(state["user_profile"])
        nutrition_plan = NutritionPlan.model_validate(state["nutrition_plan"])
        inputs = MealSelectorInputs(
            preferences=PreferenceSummary.model_validate(state["user_preferences_learned"]),
            repair_instructions=list(state["repair_instructions"]),
            blocked_recipe_ids=set(state["blocked_recipe_ids"]),
            avoid_cuisines=set(state["avoid_cuisines"]),
        )
        context = await self.context_assembler.build_context("meal_selector", state)
        prompt_template = PROMPT_PATH.read_text(encoding="utf-8").strip()
        assert prompt_template

        slot_candidates = await self._collect_slot_candidates(profile=profile, inputs=inputs)
        selected_meals, decision_sources = await self._select_weekly_plan(
            nutrition_plan=nutrition_plan,
            inputs=inputs,
            slot_candidates=slot_candidates,
            prompt_template=prompt_template,
            assembled_context=context.payload,
        )
        llm_used = any(source == "llm" for source in decision_sources.values())
        for meal in selected_meals:
            decision_source = decision_sources[self._slot_id(day=meal.day, meal_type=meal.meal_type)]
            await emit_run_event(
                run_id=state["run_id"],
                event_type="node_completed",
                phase="planning",
                node_name="meal_selector",
                message="Selected {recipe} for {day} {meal_type}.".format(
                    recipe=meal.recipe_name,
                    day=meal.day.title(),
                    meal_type=meal.meal_type,
                ),
                data={
                    "day": meal.day,
                    "meal_type": meal.meal_type,
                    "recipe_name": meal.recipe_name,
                    "decision_source": decision_source,
                },
            )

        metadata = ContextMetadata(
            node_name="meal_selector",
            tokens_used=context.budget.tokens_used,
            token_budget=context.budget.token_budget,
            fields_included=context.budget.fields_included,
            fields_dropped=context.budget.fields_dropped,
            retrieved_memory_ids=[memory.memory_id for memory in context.retrieved_memories],
        )

        return {
            "selected_meals": [meal.model_dump(mode="json") for meal in selected_meals],
            "context_metadata": [metadata.model_dump(mode="json")],
            "messages": [
                AIMessage(
                    content=(
                        "Built a {mode} weekly plan using prompt template {template}: {summary}"
                    ).format(
                        mode="LLM-guided" if llm_used else "retrieval-backed fallback",
                        template=PROMPT_PATH.name,
                        summary=prompt_template.splitlines()[0],
                    )
                )
            ],
        }

    async def _collect_slot_candidates(
        self,
        profile: UserProfileBase,
        inputs: MealSelectorInputs,
    ) -> list[MealCandidateSet]:
        slots: list[MealRequest] = []
        for day_index, day in enumerate(DAYS):
            for meal_type in ("breakfast", "lunch", "dinner", "snack"):
                slots.append(
                    MealRequest(
                        day=day,
                        day_index=day_index,
                        meal_type=meal_type,
                        max_prep_time=self._prep_cap(profile, meal_type, day),
                        query=self._build_query(profile, meal_type, day_index, inputs),
                    )
                )

        candidate_batches = await asyncio.gather(
            *(
                self._search_candidates_for_slot(profile=profile, slot=slot, inputs=inputs)
                for slot in slots
            )
        )
        return [
            MealCandidateSet(
                slot=slot,
                candidates=candidates,
                candidate_recipes=[RecipeRecord.model_validate(candidate["recipe"]) for candidate in candidates],
            )
            for slot, candidates in zip(slots, candidate_batches)
        ]

    async def _search_candidates_for_slot(
        self,
        profile: UserProfileBase,
        slot: MealRequest,
        inputs: MealSelectorInputs,
    ) -> list[Dict[str, Any]]:
        filters = {
            "meal_type": slot.meal_type,
            "max_prep_time": slot.max_prep_time,
            "dietary_tags": profile.dietary_restrictions,
            "excluded_ingredients": expand_allergy_terms(profile.allergies) + inputs.preferences.avoided_ingredients,
        }
        search_context = {
            "preferred_cuisines": inputs.preferences.preferred_cuisines,
            "avoided_ingredients": inputs.preferences.avoided_ingredients,
            "avoid_cuisines": sorted(inputs.avoid_cuisines),
            "blocked_recipe_ids": sorted(inputs.blocked_recipe_ids),
            "max_prep_time": slot.max_prep_time,
        }
        candidates = await self.recipe_search.search(
            query=slot.query,
            filters=filters,
            top_k=6,
            context=search_context,
        )
        if not candidates:
            relaxed_filters = dict(filters)
            relaxed_filters.pop("max_prep_time", None)
            candidates = await self.recipe_search.search(
                query=slot.query,
                filters=relaxed_filters,
                top_k=6,
                context=search_context,
            )
        if not candidates:
            raise ValueError("Recipe search returned no candidates for {meal_type}.".format(meal_type=slot.meal_type))
        return candidates

    def _build_query(
        self,
        profile: UserProfileBase,
        meal_type: MealType,
        day_index: int,
        inputs: MealSelectorInputs,
    ) -> str:
        preferred_cuisines = inputs.preferences.preferred_cuisines
        cuisine_hint = preferred_cuisines[day_index % len(preferred_cuisines)] if preferred_cuisines else ""
        repair_hint = " ".join(inputs.repair_instructions)
        schedule = "quick" if meal_type != "dinner" else "balanced"
        parts = [
            profile.goal,
            meal_type,
            "high protein" if meal_type != "snack" else "balanced snack",
            schedule,
            cuisine_hint,
            repair_hint,
        ]
        return " ".join(part for part in parts if part).strip()

    async def _select_weekly_plan(
        self,
        nutrition_plan: NutritionPlan,
        inputs: MealSelectorInputs,
        slot_candidates: list[MealCandidateSet],
        prompt_template: str,
        assembled_context: Dict[str, Any],
    ) -> tuple[list[MealSlot], dict[str, str]]:
        llm_recipes = await self._pick_weekly_plan_with_llm(
            slot_candidates=slot_candidates,
            nutrition_plan=nutrition_plan,
            inputs=inputs,
            prompt_template=prompt_template,
            assembled_context=assembled_context,
        )
        if llm_recipes is not None:
            selected_meals = [
                self._build_meal_slot(
                    recipe=llm_recipes[candidate_set.slot.slot_id],
                    nutrition_plan=nutrition_plan,
                    meal_type=candidate_set.slot.meal_type,
                    day=candidate_set.slot.day,
                )
                for candidate_set in slot_candidates
            ]
            return selected_meals, {
                candidate_set.slot.slot_id: "llm"
                for candidate_set in slot_candidates
            }

        selected_meals: list[MealSlot] = []
        decision_sources: dict[str, str] = {}
        for candidate_set in slot_candidates:
            recipe = self._pick_best_recipe(
                candidate_set=candidate_set,
                selected_meals=selected_meals,
                inputs=inputs,
            )
            selected_meals.append(
                self._build_meal_slot(
                    recipe=recipe,
                    nutrition_plan=nutrition_plan,
                    meal_type=candidate_set.slot.meal_type,
                    day=candidate_set.slot.day,
                )
            )
            decision_sources[candidate_set.slot.slot_id] = "deterministic_fallback"

        return selected_meals, decision_sources

    async def _pick_weekly_plan_with_llm(
        self,
        slot_candidates: list[MealCandidateSet],
        nutrition_plan: NutritionPlan,
        inputs: MealSelectorInputs,
        prompt_template: str,
        assembled_context: Dict[str, Any],
    ) -> Optional[dict[str, RecipeRecord]]:
        if self.chat_model is None:
            return None

        payload = {
            "context": assembled_context,
            "weekly_rules": {
                "blocked_recipe_ids": sorted(inputs.blocked_recipe_ids),
                "avoid_cuisines": sorted(inputs.avoid_cuisines),
                "repair_instructions": inputs.repair_instructions,
                "prefer_variety_across_adjacent_days": True,
                "keep_snacks_simple": True,
            },
            "meal_slots": [
                self._slot_payload(
                    candidate_set=candidate_set,
                    nutrition_plan=nutrition_plan,
                )
                for candidate_set in slot_candidates
            ],
        }
        decision = await invoke_structured(
            self.chat_model,
            WeeklyMealSelectionDecision,
            [
                SystemMessage(content=prompt_template),
                HumanMessage(content=json.dumps(payload, indent=2, ensure_ascii=True)),
            ],
        )

        if decision is None or len(decision.selections) != len(slot_candidates):
            return None

        selected_recipes: dict[str, RecipeRecord] = {}
        slot_lookup = {candidate_set.slot.slot_id: candidate_set for candidate_set in slot_candidates}
        for selection in decision.selections:
            candidate_set = slot_lookup.get(selection.slot_id)
            if candidate_set is None or selection.slot_id in selected_recipes:
                return None

            recipe_lookup = {
                recipe.recipe_id: recipe
                for recipe in candidate_set.candidate_recipes[:LLM_CANDIDATE_LIMIT]
            }
            recipe = recipe_lookup.get(selection.recipe_id)
            if recipe is None:
                return None
            if recipe.recipe_id in inputs.blocked_recipe_ids:
                return None
            if recipe.cuisine in inputs.avoid_cuisines:
                return None
            selected_recipes[selection.slot_id] = recipe

        if len(selected_recipes) != len(slot_candidates):
            return None

        return selected_recipes

    def _slot_payload(
        self,
        candidate_set: MealCandidateSet,
        nutrition_plan: NutritionPlan,
    ) -> Dict[str, Any]:
        calorie_target = round(nutrition_plan.daily_calories * MEAL_TARGET_SPLITS[candidate_set.slot.meal_type])
        protein_target = round(nutrition_plan.protein_g * MEAL_TARGET_SPLITS[candidate_set.slot.meal_type])
        return {
            "slot_id": candidate_set.slot.slot_id,
            "day": candidate_set.slot.day,
            "meal_type": candidate_set.slot.meal_type,
            "day_index": candidate_set.slot.day_index,
            "max_prep_time": candidate_set.slot.max_prep_time,
            "meal_calorie_target": calorie_target,
            "meal_protein_target": protein_target,
            "query": candidate_set.slot.query,
            "constraints": {
                "same_slot_only": True,
            },
            "candidates": self._candidate_payload(candidate_set, calorie_target=calorie_target, protein_target=protein_target),
        }

    def _candidate_payload(
        self,
        candidate_set: MealCandidateSet,
        calorie_target: int,
        protein_target: int,
    ) -> List[Dict[str, Any]]:
        payload: List[Dict[str, Any]] = []
        llm_candidates = list(zip(candidate_set.candidates, candidate_set.candidate_recipes))[:LLM_CANDIDATE_LIMIT]
        for candidate, recipe in llm_candidates:
            projected_serving_multiplier = max(0.85, min(1.8, calorie_target / float(recipe.calories)))
            projected_calories = int(round(recipe.calories * projected_serving_multiplier))
            projected_protein = int(round(recipe.protein_g * projected_serving_multiplier))
            projected_carbs = int(round(recipe.carbs_g * projected_serving_multiplier))
            projected_fat = int(round(recipe.fat_g * projected_serving_multiplier))
            payload.append(
                {
                    "recipe_id": recipe.recipe_id,
                    "name": recipe.name,
                    "cuisine": recipe.cuisine,
                    "prep_time_min": recipe.prep_time_min,
                    "calories": recipe.calories,
                    "protein_g": recipe.protein_g,
                    "carbs_g": recipe.carbs_g,
                    "fat_g": recipe.fat_g,
                    "tags": recipe.tags,
                    "rerank_score": candidate["rerank_score"],
                    "reasons": candidate.get("reasons", []),
                    "projected_serving_multiplier": round(projected_serving_multiplier, 2),
                    "projected_calories": projected_calories,
                    "projected_protein_g": projected_protein,
                    "projected_carbs_g": projected_carbs,
                    "projected_fat_g": projected_fat,
                    "macro_fit_score": self._macro_fit_score(
                        calorie_target=calorie_target,
                        actual_calories=projected_calories,
                        target_protein=protein_target,
                        actual_protein=projected_protein,
                    ),
                }
            )
        return payload

    def _pick_best_recipe(
        self,
        candidate_set: MealCandidateSet,
        selected_meals: List[MealSlot],
        inputs: MealSelectorInputs,
    ) -> RecipeRecord:
        if not candidate_set.candidates:
            raise ValueError(
                "Recipe search returned no candidates for {meal_type}.".format(meal_type=candidate_set.slot.meal_type)
            )

        slot = candidate_set.slot
        candidate_recipes = candidate_set.candidate_recipes
        recent_recipe_ids = {
            meal.recipe_id
            for meal in selected_meals
            if meal.meal_type == slot.meal_type and meal.day in DAYS[max(0, slot.day_index - 2):slot.day_index]
        }
        recent_cuisines = {
            meal.cuisine
            for meal in selected_meals
            if meal.day in DAYS[max(0, slot.day_index - 2):slot.day_index]
        }
        best_candidate = None
        best_score = float("-inf")
        disallowed_recipe_ids = {
            meal.recipe_id
            for meal in selected_meals
            if meal.macro_fit_score < 0.55
        }

        strict_candidates = [
            recipe
            for recipe in candidate_recipes
            if recipe.recipe_id not in inputs.blocked_recipe_ids
            and recipe.recipe_id not in disallowed_recipe_ids
            and recipe.recipe_id not in recent_recipe_ids
            and recipe.cuisine not in recent_cuisines
            and recipe.cuisine not in inputs.avoid_cuisines
        ]
        if strict_candidates:
            return strict_candidates[0]

        for candidate, recipe in zip(candidate_set.candidates, candidate_recipes):
            score = float(candidate["rerank_score"])
            if recipe.recipe_id in inputs.blocked_recipe_ids or recipe.recipe_id in disallowed_recipe_ids:
                continue
            if recipe.cuisine in inputs.avoid_cuisines:
                score -= 0.45
            if recipe.recipe_id in recent_recipe_ids:
                score -= 0.6
            if recipe.cuisine in recent_cuisines:
                score -= 0.5
            if any(previous.recipe_id == recipe.recipe_id for previous in selected_meals):
                score -= 0.2
            if score > best_score:
                best_candidate = recipe
                best_score = score

        if best_candidate is None:
            return candidate_recipes[0]
        return best_candidate

    def _slot_id(self, day: str, meal_type: MealType) -> str:
        return "{day}:{meal_type}".format(day=day, meal_type=meal_type)

    def _build_meal_slot(
        self,
        recipe: RecipeRecord,
        nutrition_plan: NutritionPlan,
        meal_type: MealType,
        day: str,
    ) -> MealSlot:
        calorie_target = nutrition_plan.daily_calories * MEAL_TARGET_SPLITS[meal_type]
        serving_multiplier = max(0.85, min(1.8, calorie_target / float(recipe.calories)))
        calories = int(round(recipe.calories * serving_multiplier))
        protein_g = int(round(recipe.protein_g * serving_multiplier))
        carbs_g = int(round(recipe.carbs_g * serving_multiplier))
        fat_g = int(round(recipe.fat_g * serving_multiplier))

        macro_fit_score = self._macro_fit_score(
            calorie_target=calorie_target,
            actual_calories=calories,
            target_protein=nutrition_plan.protein_g * MEAL_TARGET_SPLITS[meal_type],
            actual_protein=protein_g,
        )

        return MealSlot(
            day=day,
            meal_type=meal_type,
            recipe_id=recipe.recipe_id,
            recipe_name=recipe.name,
            cuisine=recipe.cuisine,
            prep_time_min=recipe.prep_time_min,
            serving_multiplier=round(serving_multiplier, 2),
            calories=calories,
            protein_g=protein_g,
            carbs_g=carbs_g,
            fat_g=fat_g,
            tags=recipe.tags,
            macro_fit_score=macro_fit_score,
            recipe=recipe,
        )

    def _macro_fit_score(
        self,
        calorie_target: float,
        actual_calories: int,
        target_protein: float,
        actual_protein: int,
    ) -> float:
        calorie_delta = abs(actual_calories - calorie_target) / max(calorie_target, 1.0)
        protein_delta = abs(actual_protein - target_protein) / max(target_protein, 1.0)
        score = 1.0 - ((calorie_delta * 0.65) + (protein_delta * 0.35))
        return round(max(0.0, min(1.0, score)), 3)

    def _prep_cap(self, profile: UserProfileBase, meal_type: MealType, day: str) -> int:
        defaults = {"breakfast": 15, "lunch": 20, "dinner": 35, "snack": 10}
        if meal_type != "dinner":
            return defaults[meal_type]

        schedule = {str(key).lower(): str(value).lower() for key, value in profile.schedule_json.items()}
        matching_entries = [
            value
            for key, value in schedule.items()
            if day[:3] in key or day in key or "weeknight" in key or "weekday" in key
        ]
        if "saturday" in day or "sunday" in day:
            matching_entries.extend(
                value for key, value in schedule.items() if "weekend" in key or "saturday" in key or "sunday" in key
            )

        for entry in matching_entries:
            digits = "".join(character for character in entry if character.isdigit())
            if digits:
                return max(15, int(digits))
            if "quick" in entry:
                return 25
            if "flex" in entry or "slow" in entry:
                return 45

        return defaults[meal_type]
