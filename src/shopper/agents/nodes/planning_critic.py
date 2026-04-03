from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from shopper.agents.events import emit_run_event
from shopper.agents.llm import invoke_structured
from shopper.agents.nodes.critic_common import CriticAssessment, build_findings, dedupe_findings, dedupe_strings
from shopper.memory import ContextAssembler
from shopper.retrieval import QdrantRecipeStore
from shopper.schemas import ContextMetadata, CriticFinding, CriticVerdict, MealSlot, NutritionPlan
from shopper.validators import (
    validate_daily_macro_alignment,
    validate_meal_plan_safety,
    validate_meal_plan_schedule_fit,
    validate_meal_plan_slot_coverage,
    validate_nutrition_plan,
)


PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "planning_critic.md"


@dataclass
class PlanningCriticNode:
    context_assembler: ContextAssembler
    recipe_store: QdrantRecipeStore
    chat_model: Optional[Any] = None

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_entered",
            phase="planning",
            node_name="critic",
            message="Reviewing plan coverage, macro alignment, safety, and groundedness.",
        )

        context = await self.context_assembler.build_context("planning_critic", state)
        nutrition_plan = NutritionPlan.model_validate(state["nutrition_plan"])
        meals = [MealSlot.model_validate(item) for item in state["selected_meals"]]
        user_profile = state["user_profile"]

        findings = dedupe_findings(
            [
                *build_findings("P_PLAN_INVALID", validate_nutrition_plan(nutrition_plan), severity="issue"),
                *build_findings("P_SLOT_COVERAGE", validate_meal_plan_slot_coverage(meals), severity="issue"),
                *build_findings(
                    "P_MACRO_MISS",
                    validate_daily_macro_alignment(nutrition_plan, meals, "critic_blockers"),
                    severity="issue",
                ),
                *build_findings(
                    "P_MACRO_DRIFT",
                    validate_daily_macro_alignment(nutrition_plan, meals, "critic_warnings"),
                    severity="warning",
                ),
                *build_findings(
                    "P_SAFETY",
                    validate_meal_plan_safety(meals, user_profile["allergies"]),
                    severity="issue",
                ),
                *build_findings("P_GROUNDEDNESS", self._groundedness_issues(meals), severity="issue"),
                *build_findings(
                    "P_SCHEDULE",
                    validate_meal_plan_schedule_fit(meals, user_profile["schedule_json"]),
                    severity="issue",
                ),
                *build_findings("P_VARIETY", self._variety_warnings(meals), severity="warning"),
            ]
        )

        llm_assessment = await self._llm_review(context.payload, nutrition_plan, meals)
        if llm_assessment is not None:
            findings = dedupe_findings(
                [
                    *findings,
                    *build_findings("P_LLM_REVIEW", llm_assessment.issues, severity="issue"),
                    *build_findings("P_LLM_REVIEW", llm_assessment.warnings, severity="warning"),
                ]
            )

        issues = [finding.message for finding in findings if finding.severity == "issue"]
        warnings = [finding.message for finding in findings if finding.severity == "warning"]
        verdict = CriticVerdict(
            passed=not issues and (llm_assessment.passed if llm_assessment is not None else True),
            issues=issues,
            warnings=warnings,
            repair_instructions=dedupe_strings(
                self._repair_instructions(findings)
                + (llm_assessment.repair_instructions if llm_assessment is not None else [])
            ),
            findings=findings,
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
            phase="planning",
            node_name="critic",
            message="Planning critic {result} with {issue_count} blocking issues.".format(
                result="passed" if verdict.passed else "failed",
                issue_count=len(verdict.issues),
            ),
            data={
                "passed": verdict.passed,
                "issues": verdict.issues,
                "warnings": verdict.warnings,
                "finding_codes": [finding.code for finding in verdict.findings],
            },
        )

        return {
            "critic_verdict": verdict.model_dump(mode="json"),
            "repair_instructions": verdict.repair_instructions,
            "context_metadata": [metadata.model_dump(mode="json")],
            "messages": [
                AIMessage(
                    content="Planning critic review complete with {mode}.".format(
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
        recent_recipe_ids: Dict[str, List[str]] = {}
        for meal in meals:
            recent_cuisines = []
            recent_recipes = []
            for cuisines in list(seen_by_day.values())[-2:]:
                recent_cuisines.extend(cuisines)
            for recipe_ids in list(recent_recipe_ids.values())[-2:]:
                recent_recipes.extend(recipe_ids)
            if meal.cuisine and meal.cuisine in recent_cuisines:
                warnings.append(
                    "Cuisine repeat detected for {cuisine} around {day}.".format(
                        cuisine=meal.cuisine,
                        day=meal.day,
                    )
                )
            if meal.recipe_id in recent_recipes:
                warnings.append(
                    "Recipe repeat detected for {recipe_id} around {day}.".format(
                        recipe_id=meal.recipe_id,
                        day=meal.day,
                    )
                )
            seen_by_day.setdefault(meal.day, []).append(meal.cuisine)
            recent_recipe_ids.setdefault(meal.day, []).append(meal.recipe_id)
        return dedupe_strings(warnings)

    def _repair_instructions(self, findings: List[CriticFinding]) -> List[str]:
        codes = {finding.code for finding in findings if finding.severity == "issue"}
        instructions: List[str] = []
        if "P_SLOT_COVERAGE" in codes:
            instructions.append("Fill every missing meal slot exactly once before handing off to shopping.")
        if "P_SAFETY" in codes:
            instructions.append("Replace any meal containing a flagged allergen before finalizing the plan.")
        if "P_GROUNDEDNESS" in codes:
            instructions.append("Select only recipes that resolve from the recipe store and keep nutrition grounded to recipe evidence.")
        if "P_MACRO_MISS" in codes or "P_PLAN_INVALID" in codes:
            instructions.append("Rebalance the affected days so the selected meals match the daily calorie and macro targets.")
        if "P_SCHEDULE" in codes:
            instructions.append("Swap meals that exceed weekday or weekend prep limits for faster alternatives.")
        if "P_VARIETY" in {finding.code for finding in findings}:
            instructions.append("Increase variety across adjacent days and avoid repeating the same cuisine or recipe too tightly.")
        return instructions
