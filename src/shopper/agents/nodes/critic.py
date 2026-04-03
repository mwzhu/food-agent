from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from shopper.agents.events import emit_run_event
from shopper.agents.llm import invoke_structured
from shopper.memory import ContextAssembler
from shopper.retrieval import QdrantRecipeStore
from shopper.schemas import ContextMetadata, CriticVerdict, GroceryItem, MealSlot, NutritionPlan
from shopper.validators import validate_grocery_list, validate_meal_plan_safety, validate_nutrition_plan


PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "critic.md"


class CriticAssessment(BaseModel):
    passed: bool = True
    issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    repair_instructions: List[str] = Field(default_factory=list)


@dataclass
class CriticNode:
    context_assembler: ContextAssembler
    recipe_store: QdrantRecipeStore
    chat_model: Optional[Any] = None

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        phase = state.get("current_phase", "planning")
        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_entered",
            phase=phase,
            node_name="critic",
            message=(
                "Reviewing nutrition, safety, and recipe groundedness."
                if phase == "planning"
                else "Reviewing grocery completeness against the approved meal plan."
            ),
        )

        context = await self.context_assembler.build_context("critic", state)
        nutrition_plan = NutritionPlan.model_validate(state["nutrition_plan"])
        meals = [MealSlot.model_validate(item) for item in state["selected_meals"]]
        grocery_list = [GroceryItem.model_validate(item) for item in state.get("grocery_list", [])]
        nutrition_plan_issues = validate_nutrition_plan(nutrition_plan)
        user_profile = state["user_profile"]
        safety_issues = validate_meal_plan_safety(meals, user_profile["allergies"])
        groundedness_issues = self._groundedness_issues(meals)
        grocery_issues = validate_grocery_list(meals, grocery_list) if phase == "shopping" else []
        llm_assessment = await self._llm_review(context.payload, nutrition_plan, meals)
        warnings = self._dedupe(self._variety_warnings(meals) + (llm_assessment.warnings if llm_assessment else []))
        issues = self._dedupe(
            nutrition_plan_issues
            + safety_issues
            + groundedness_issues
            + grocery_issues
            + (llm_assessment.issues if llm_assessment else [])
        )
        verdict = CriticVerdict(
            passed=not issues and (llm_assessment.passed if llm_assessment is not None else True),
            issues=issues,
            warnings=warnings,
            repair_instructions=self._dedupe(
                self._repair_instructions(issues)
                + (llm_assessment.repair_instructions if llm_assessment is not None else [])
            ),
        )
        metadata = ContextMetadata(
            node_name="critic",
            tokens_used=context.budget.tokens_used,
            token_budget=context.budget.token_budget,
            fields_included=context.budget.fields_included,
            fields_dropped=context.budget.fields_dropped,
            retrieved_memory_ids=[],
        )

        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_completed",
            phase=phase,
            node_name="critic",
            message="{phase} critic {result} with {issue_count} blocking issues.".format(
                phase=str(phase).title(),
                result="passed" if verdict.passed else "failed",
                issue_count=len(verdict.issues),
            ),
            data={"passed": verdict.passed, "issues": verdict.issues, "warnings": verdict.warnings},
        )

        return {
            "critic_verdict": verdict.model_dump(mode="json"),
            "repair_instructions": verdict.repair_instructions,
            "context_metadata": [metadata.model_dump(mode="json")],
            "messages": [
                AIMessage(
                    content="Critic review complete with {mode}.".format(
                        mode="LLM support" if llm_assessment is not None else "deterministic fallback"
                    )
                )
            ],
        }

    async def _llm_review(
        self,
        context_payload: Dict[str, Any],
        nutrition_plan: NutritionPlan,
        meals: List[MealSlot],
    ) -> Optional[CriticAssessment]:
        if self.chat_model is None or not meals:
            return None

        prompt_template = PROMPT_PATH.read_text(encoding="utf-8").strip()
        evidence = {
            "context": context_payload,
            "nutrition_plan": nutrition_plan.model_dump(mode="json"),
            "meal_plan": [self._meal_evidence(meal) for meal in meals],
        }
        return await invoke_structured(
            self.chat_model,
            CriticAssessment,
            [
                SystemMessage(content=prompt_template),
                HumanMessage(content=json.dumps(evidence, indent=2, ensure_ascii=True)),
            ],
        )

    def _meal_evidence(self, meal: MealSlot) -> Dict[str, Any]:
        source_recipe = self.recipe_store.get_recipe(meal.recipe_id)
        recipe = meal.recipe or source_recipe
        return {
            "day": meal.day,
            "meal_type": meal.meal_type,
            "recipe_id": meal.recipe_id,
            "recipe_name": meal.recipe_name,
            "meal_slot": {
                "cuisine": meal.cuisine,
                "prep_time_min": meal.prep_time_min,
                "serving_multiplier": meal.serving_multiplier,
                "calories": meal.calories,
                "protein_g": meal.protein_g,
                "carbs_g": meal.carbs_g,
                "fat_g": meal.fat_g,
                "tags": meal.tags,
                "macro_fit_score": meal.macro_fit_score,
            },
            "source_recipe": recipe.model_dump(mode="json") if recipe is not None else None,
        }

    def _groundedness_issues(self, meals: List[MealSlot]) -> List[str]:
        issues: List[str] = []
        for meal in meals:
            recipe = self.recipe_store.get_recipe(meal.recipe_id)
            if recipe is None:
                issues.append("Recipe {recipe_id} is missing from the retrieval store.".format(recipe_id=meal.recipe_id))
                continue

            expected_calories = int(round(recipe.calories * meal.serving_multiplier))
            expected_protein = int(round(recipe.protein_g * meal.serving_multiplier))
            expected_carbs = int(round(recipe.carbs_g * meal.serving_multiplier))
            expected_fat = int(round(recipe.fat_g * meal.serving_multiplier))
            if (
                abs(meal.calories - expected_calories) > 15
                or abs(meal.protein_g - expected_protein) > 4
                or abs(meal.carbs_g - expected_carbs) > 4
                or abs(meal.fat_g - expected_fat) > 4
            ):
                issues.append(
                    "Meal slot {recipe_id} drifted too far from the recipe source nutrition.".format(
                        recipe_id=meal.recipe_id
                    )
                )
        return issues

    def _variety_warnings(self, meals: List[MealSlot]) -> List[str]:
        warnings: List[str] = []
        seen_by_day: Dict[str, List[str]] = {}
        for meal in meals:
            recent_cuisines = []
            for cuisines in list(seen_by_day.values())[-2:]:
                recent_cuisines.extend(cuisines)
            if meal.cuisine and meal.cuisine in recent_cuisines:
                warnings.append(
                    "Cuisine repeat detected for {cuisine} around {day}.".format(
                        cuisine=meal.cuisine,
                        day=meal.day,
                    )
                )
            seen_by_day.setdefault(meal.day, []).append(meal.cuisine)
        return self._dedupe(warnings)

    def _repair_instructions(self, issues: List[str]) -> List[str]:
        instructions: List[str] = []
        lowered_issues = [issue.lower() for issue in issues]
        if any("allergen" in issue for issue in lowered_issues):
            instructions.append("Replace any meal containing a flagged allergen before finalizing the plan.")
        if any("missing from the retrieval store" in issue for issue in lowered_issues):
            instructions.append("Select only recipes that resolve from the recipe store.")
        if any("nutrition" in issue or "macro" in issue for issue in lowered_issues):
            instructions.append("Rebalance meal portions so macro totals stay consistent with the nutrition plan.")
        if any("prep" in issue or "schedule" in issue for issue in lowered_issues):
            instructions.append("Match prep times to the user's weekday and weekend schedule constraints.")
        if any("repeat" in issue or "variety" in issue or "cuisine" in issue for issue in lowered_issues):
            instructions.append("Increase variety across adjacent days and avoid recently repeated cuisines.")
        return instructions

    def _dedupe(self, values: List[str]) -> List[str]:
        return list(dict.fromkeys(value for value in values if value))
