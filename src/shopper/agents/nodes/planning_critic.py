from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from shopper.agents.events import emit_run_event
from shopper.agents.llm import invoke_structured
from shopper.agents.nodes.critic_common import CriticAssessment, build_findings, dedupe_findings, dedupe_strings
from shopper.memory import ContextAssembler
from shopper.retrieval import QdrantRecipeStore
from shopper.schemas import (
    BudgetSummary,
    ContextMetadata,
    CriticFinding,
    CriticVerdict,
    FridgeItemSnapshot,
    GroceryItem,
    MealSlot,
    NutritionPlan,
    PurchaseOrder,
    StoreSummary,
)
from shopper.validators import (
    validate_daily_macro_alignment,
    validate_fridge_inventory_consistency,
    validate_grocery_aggregation,
    validate_grocery_fridge_diff,
    validate_grocery_list,
    validate_grocery_traceability,
    validate_meal_plan_safety,
    validate_meal_plan_schedule_fit,
    validate_nutrition_plan,
)


PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "planning_critic.md"
TIME_CONSTRAINED_KEYWORDS = ("quick", "busy", "15", "20", "30")


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
            message="Reviewing the full pre-checkout package for nutrition, safety, groundedness, grocery coverage, and budget fit.",
        )

        context = await self.context_assembler.build_context("critic", state)
        nutrition_plan = NutritionPlan.model_validate(state["nutrition_plan"])
        meals = [MealSlot.model_validate(item) for item in state["selected_meals"]]
        grocery_list = [GroceryItem.model_validate(item) for item in state.get("grocery_list", [])]
        fridge_inventory = [FridgeItemSnapshot.model_validate(item) for item in state.get("fridge_inventory", [])]
        store_summaries = [StoreSummary.model_validate(item) for item in state.get("store_summaries", [])]
        purchase_orders = [PurchaseOrder.model_validate(item) for item in state.get("purchase_orders", [])]
        budget_summary = (
            BudgetSummary.model_validate(state["budget_summary"])
            if state.get("budget_summary") is not None
            else None
        )

        store_choice_issues, store_choice_warnings = self._validate_store_choice_reasonableness(
            grocery_list=grocery_list,
            store_summaries=store_summaries,
            purchase_orders=purchase_orders,
            budget_summary=budget_summary,
            price_strategy=state.get("price_strategy"),
            schedule_json=state["user_profile"]["schedule_json"],
        )
        findings = dedupe_findings(
            [
                *build_findings("P_NUTRITION_PLAN", validate_nutrition_plan(nutrition_plan), severity="issue"),
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
                    validate_meal_plan_safety(meals, state["user_profile"]["allergies"]),
                    severity="issue",
                ),
                *build_findings("P_GROUNDEDNESS", self._groundedness_issues(meals), severity="issue"),
                *build_findings(
                    "P_SCHEDULE",
                    validate_meal_plan_schedule_fit(meals, state["user_profile"]["schedule_json"]),
                    severity="issue",
                ),
                *build_findings("P_VARIETY", self._variety_warnings(meals), severity="warning"),
                *build_findings(
                    "P_GROCERY_COVERAGE",
                    self._grocery_coverage_issues(meals, grocery_list, fridge_inventory),
                    severity="issue",
                ),
                *build_findings(
                    "P_GROCERY_TRACEABILITY",
                    validate_grocery_traceability(meals, grocery_list),
                    severity="issue",
                ),
                *build_findings(
                    "P_PURCHASE_COVERAGE",
                    self._validate_purchase_order_coverage(grocery_list, purchase_orders),
                    severity="issue",
                ),
                *build_findings(
                    "P_BUDGET",
                    self._validate_budget(grocery_list, budget_summary),
                    severity="issue",
                ),
                *build_findings("P_STORE_CHOICE", store_choice_issues, severity="issue"),
                *build_findings("P_STORE_CHOICE", store_choice_warnings, severity="warning"),
            ]
        )

        llm_assessment = await self._llm_review(
            context_payload=context.payload,
            nutrition_plan=nutrition_plan,
            meals=meals,
            grocery_list=grocery_list,
            fridge_inventory=fridge_inventory,
            store_summaries=store_summaries,
            purchase_orders=purchase_orders,
            budget_summary=budget_summary,
            replan_reason=state.get("replan_reason"),
            price_strategy=state.get("price_strategy"),
            price_rationale=state.get("price_rationale"),
        )
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
        *,
        context_payload: Dict[str, Any],
        nutrition_plan: NutritionPlan,
        meals: List[MealSlot],
        grocery_list: List[GroceryItem],
        fridge_inventory: List[FridgeItemSnapshot],
        store_summaries: List[StoreSummary],
        purchase_orders: List[PurchaseOrder],
        budget_summary: Optional[BudgetSummary],
        replan_reason: Optional[str],
        price_strategy: Optional[str],
        price_rationale: Optional[str],
    ) -> Optional[CriticAssessment]:
        if self.chat_model is None or not meals:
            return None

        prompt_template = PROMPT_PATH.read_text(encoding="utf-8").strip()
        evidence = {
            "context": context_payload,
            "nutrition_plan": nutrition_plan.model_dump(mode="json"),
            "meal_plan": [self._meal_evidence(meal) for meal in meals],
            "grocery_list": [item.model_dump(mode="json") for item in grocery_list],
            "fridge_inventory": [item.model_dump(mode="json") for item in fridge_inventory],
            "store_summaries": [summary.model_dump(mode="json") for summary in store_summaries],
            "purchase_orders": [order.model_dump(mode="json") for order in purchase_orders],
            "budget_summary": budget_summary.model_dump(mode="json") if budget_summary is not None else None,
            "pricing": {
                "strategy": price_strategy,
                "rationale": price_rationale,
                "replan_reason": replan_reason,
            },
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

    def _grocery_coverage_issues(
        self,
        meals: Sequence[MealSlot],
        grocery_list: Sequence[GroceryItem],
        fridge_inventory: Sequence[FridgeItemSnapshot],
    ) -> List[str]:
        return dedupe_strings(
            validate_grocery_list(meals, grocery_list)
            + validate_grocery_aggregation(meals, grocery_list)
            + validate_grocery_fridge_diff(meals, grocery_list, fridge_inventory)
            + validate_fridge_inventory_consistency(grocery_list, fridge_inventory)
        )

    def _validate_purchase_order_coverage(
        self,
        grocery_list: Sequence[GroceryItem],
        purchase_orders: Sequence[PurchaseOrder],
    ) -> List[str]:
        required_counts = Counter(
            self._coverage_key(item.name, item.unit, item.shopping_quantity)
            for item in grocery_list
            if not item.already_have and item.shopping_quantity > 0
        )
        if not required_counts:
            return []

        covered_counts = Counter(
            self._coverage_key(order_item.name, order_item.unit, order_item.quantity)
            for order in purchase_orders
            for order_item in order.items
        )
        findings: List[str] = []
        for item_key, required_count in sorted(required_counts.items()):
            if covered_counts.get(item_key, 0) < required_count:
                findings.append(
                    "Missing purchase order coverage for '{item_name}'.".format(
                        item_name=item_key.split("|", 1)[0]
                    )
                )
            if covered_counts.get(item_key, 0) > required_count:
                findings.append(
                    "Purchase orders include '{item_name}' more than once.".format(
                        item_name=item_key.split("|", 1)[0]
                    )
                )
        return findings

    def _validate_budget(
        self,
        grocery_list: Sequence[GroceryItem],
        budget_summary: Optional[BudgetSummary],
    ) -> List[str]:
        required_items = [
            item
            for item in grocery_list
            if not item.already_have and item.shopping_quantity > 0
        ]
        if budget_summary is None:
            if required_items:
                return ["Budget summary is missing for a basket that still needs pricing."]
            return []
        if budget_summary.within_budget:
            return []
        return [
            "Optimized purchase orders exceed the weekly budget by ${overage:.2f}.".format(
                overage=budget_summary.overage
            )
        ]

    def _validate_store_choice_reasonableness(
        self,
        *,
        grocery_list: Sequence[GroceryItem],
        store_summaries: Sequence[StoreSummary],
        purchase_orders: Sequence[PurchaseOrder],
        budget_summary: Optional[BudgetSummary],
        price_strategy: Optional[str],
        schedule_json: Dict[str, Any],
    ) -> tuple[List[str], List[str]]:
        required_items = [
            item
            for item in grocery_list
            if not item.already_have and item.shopping_quantity > 0
        ]
        if not required_items:
            return [], []

        issues: List[str] = []
        warnings: List[str] = []
        store_summary_by_store = {summary.store: summary for summary in store_summaries}
        if not store_summaries:
            issues.append("Store summaries are missing for a basket that still needs pricing.")

        if price_strategy == "fridge_only":
            issues.append("Pricing marked the basket as fridge-only even though ingredients still need buying.")
        if price_strategy == "no_viable_plan" and purchase_orders:
            issues.append("Pricing marked the basket as unfulfillable but still returned purchase orders.")
        if purchase_orders and not price_strategy:
            warnings.append("Finalized purchase orders are missing a recorded pricing strategy.")
        if price_strategy and price_strategy.startswith("single_store") and len(purchase_orders) > 1:
            issues.append("A single-store strategy returned multiple purchase orders.")
        if price_strategy == "split_delivery" and len(purchase_orders) == 1:
            warnings.append("The recorded split-delivery strategy collapsed to a single store.")
        if not purchase_orders and price_strategy not in {None, "no_viable_plan"}:
            issues.append("Pricing returned a store strategy without any purchase orders.")

        for order in purchase_orders:
            summary = store_summary_by_store.get(order.store)
            if summary is None:
                issues.append("Purchase order store {store} is missing from the store summaries.".format(store=order.store))
                continue
            if order.channel != "in_store" and summary.min_order > 0 and order.subtotal + 1e-6 < summary.min_order:
                issues.append(
                    "Online order at {store} does not meet the store minimum order.".format(store=order.store)
                )

        if budget_summary is not None and budget_summary.within_budget:
            total_delivery_fees = round(sum(order.delivery_fee for order in purchase_orders), 2)
            schedule_text = " ".join(str(value).lower() for value in schedule_json.values())
            time_constrained = any(keyword in schedule_text for keyword in TIME_CONSTRAINED_KEYWORDS)
            if time_constrained and purchase_orders and all(order.channel == "in_store" for order in purchase_orders):
                warnings.append("The selected in-store strategy may be inconvenient for a time-constrained schedule.")
            if (not time_constrained) and total_delivery_fees > 8.0 and len(purchase_orders) > 1:
                warnings.append("The chosen channel mix pays several delivery fees for a schedule that does not appear time constrained.")

        return dedupe_strings(issues), dedupe_strings(warnings)

    def _repair_instructions(self, findings: Sequence[CriticFinding]) -> List[str]:
        issue_codes = {finding.code for finding in findings if finding.severity == "issue"}
        all_codes = {finding.code for finding in findings}
        instructions: List[str] = []
        if "P_NUTRITION_PLAN" in issue_codes:
            instructions.append("Keep the nutrition target internally consistent before selecting meals.")
        if "P_GROUNDEDNESS" in issue_codes:
            instructions.append("Select only recipes that resolve from the recipe store and keep nutrition grounded to recipe evidence.")
        if "P_MACRO_MISS" in issue_codes:
            instructions.append("Rebalance the affected days so the selected meals match the daily calorie and macro targets.")
        if "P_SAFETY" in issue_codes:
            instructions.append("Swap any unsafe meals so the plan fully respects allergy and restriction constraints.")
        if "P_SCHEDULE" in issue_codes:
            instructions.append("Swap meals that exceed weekday or weekend prep limits for faster alternatives.")
        if {"P_GROCERY_COVERAGE", "P_GROCERY_TRACEABILITY"} & issue_codes:
            instructions.append("Rebuild the grocery package so every required ingredient is covered with correct quantities and traceable recipe sources.")
        if "P_PURCHASE_COVERAGE" in issue_codes:
            instructions.append("Rerun fulfillment prep so every grocery item that still needs buying is assigned to exactly one purchase order.")
        if "P_BUDGET" in issue_codes:
            instructions.append("Choose cheaper meals and ingredients so the resulting basket fits within the weekly budget.")
        if "P_STORE_CHOICE" in issue_codes:
            instructions.append("Use store channels that respect minimum-order constraints and better match the user's schedule.")
        if "P_VARIETY" in all_codes:
            instructions.append("Increase variety across adjacent days and avoid repeating the same cuisine or recipe too tightly.")
        return instructions

    def _coverage_key(self, name: str, unit: Optional[str], quantity: float) -> str:
        return "{name}|{unit}|{quantity}".format(
            name=name.lower().strip(),
            unit=(unit or "").lower(),
            quantity=round(quantity, 2),
        )
