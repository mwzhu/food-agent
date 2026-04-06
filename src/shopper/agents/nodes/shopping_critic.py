from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from collections import Counter
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from shopper.agents.events import emit_run_event
from shopper.agents.llm import invoke_structured
from shopper.agents.nodes.critic_common import CriticAssessment, build_findings, dedupe_findings, dedupe_strings
from shopper.memory import ContextAssembler
from shopper.schemas import (
    BudgetSummary,
    ContextMetadata,
    CriticFinding,
    CriticVerdict,
    FridgeItemSnapshot,
    GroceryItem,
    MealSlot,
    PurchaseOrder,
)


PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "shopping_critic.md"


@dataclass
class ShoppingCriticNode:
    context_assembler: ContextAssembler
    chat_model: Optional[Any] = None

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_entered",
            phase="shopping",
            node_name="critic",
            message="Reviewing final purchase coverage, budget fit, and shopping-level quality.",
        )

        context = await self.context_assembler.build_context("shopping_critic", state)
        meals = [MealSlot.model_validate(item) for item in state["selected_meals"]]
        grocery_list = [GroceryItem.model_validate(item) for item in state.get("grocery_list", [])]
        fridge_inventory = [FridgeItemSnapshot.model_validate(item) for item in state.get("fridge_inventory", [])]
        purchase_orders = [PurchaseOrder.model_validate(item) for item in state.get("purchase_orders", [])]
        budget_summary = (
            BudgetSummary.model_validate(state["budget_summary"])
            if state.get("budget_summary") is not None
            else None
        )

        findings = dedupe_findings(
            [
                *build_findings(
                    "S_PRICE_COVERAGE",
                    self._validate_purchase_order_coverage(grocery_list, purchase_orders),
                    severity="issue",
                ),
                *build_findings("S_BUDGET", self._validate_budget(budget_summary), severity="issue"),
            ]
        )

        llm_assessment = await self._llm_review(
            context.payload,
            meals,
            grocery_list,
            fridge_inventory,
            purchase_orders,
            budget_summary,
        )
        if llm_assessment is not None:
            findings = dedupe_findings(
                [
                    *findings,
                    *build_findings("S_LLM_REVIEW", llm_assessment.issues, severity="issue"),
                    *build_findings("S_LLM_REVIEW", llm_assessment.warnings, severity="warning"),
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
            phase="shopping",
            node_name="critic",
            message="Shopping critic {result} with {issue_count} blocking issues.".format(
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
                    content="Shopping critic review complete with {mode}.".format(
                        mode="LLM support" if llm_assessment is not None else "deterministic fallback"
                    )
                )
            ],
        }

    async def _llm_review(
        self,
        context_payload: Dict[str, Any],
        meals: List[MealSlot],
        grocery_list: List[GroceryItem],
        fridge_inventory: List[FridgeItemSnapshot],
        purchase_orders: List[PurchaseOrder],
        budget_summary: Optional[BudgetSummary],
    ) -> Optional[CriticAssessment]:
        if self.chat_model is None or not grocery_list:
            return None

        prompt_template = PROMPT_PATH.read_text(encoding="utf-8").strip()
        evidence = {
            "context": context_payload,
            "meal_plan": [
                {
                    "day": meal.day,
                    "meal_type": meal.meal_type,
                    "recipe_id": meal.recipe_id,
                    "recipe_name": meal.recipe_name,
                }
                for meal in meals
            ],
            "grocery_list": [item.model_dump(mode="json") for item in grocery_list],
            "fridge_inventory": [item.model_dump(mode="json") for item in fridge_inventory],
            "purchase_orders": [order.model_dump(mode="json") for order in purchase_orders],
            "budget_summary": budget_summary.model_dump(mode="json") if budget_summary is not None else None,
        }
        return await invoke_structured(
            self.chat_model,
            CriticAssessment,
            [
                SystemMessage(content=prompt_template),
                HumanMessage(content=json.dumps(evidence, indent=2, ensure_ascii=True)),
            ],
        )

    def _repair_instructions(self, findings: List[CriticFinding]) -> List[str]:
        codes = {finding.code for finding in findings if finding.severity == "issue"}
        instructions: List[str] = []
        if "S_PRICE_COVERAGE" in codes:
            instructions.append("Rebuild purchase orders so every item that still needs buying is assigned to exactly one store.")
        if "S_BUDGET" in codes:
            instructions.append("Choose a lower-cost store strategy or replan meals toward cheaper ingredients until the basket fits the weekly budget.")
        return instructions

    def _validate_purchase_order_coverage(
        self,
        grocery_list: List[GroceryItem],
        purchase_orders: List[PurchaseOrder],
    ) -> List[str]:
        required_items = [
            item.name
            for item in grocery_list
            if not item.already_have and item.shopping_quantity > 0
        ]
        if not required_items:
            return []

        covered_items = [
            self._coverage_key(order_item.name, order_item.unit, order_item.quantity)
            for order in purchase_orders
            for order_item in order.items
        ]
        findings: List[str] = []
        required_counts = Counter(
            self._coverage_key(item.name, item.unit, item.shopping_quantity)
            for item in grocery_list
            if not item.already_have and item.shopping_quantity > 0
        )
        covered_counts = Counter(covered_items)
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

    def _validate_budget(self, budget_summary: Optional[BudgetSummary]) -> List[str]:
        if budget_summary is None or budget_summary.within_budget:
            return []
        return [
            "Optimized purchase orders exceed the weekly budget by ${overage:.2f}.".format(
                overage=budget_summary.overage
            )
        ]

    def _coverage_key(self, name: str, unit: Optional[str], quantity: float) -> str:
        return "{name}|{unit}|{quantity}".format(
            name=name.lower().strip(),
            unit=(unit or "").lower(),
            quantity=round(quantity, 2),
        )
