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
from shopper.schemas import ContextMetadata, CriticFinding, FridgeItemSnapshot, GroceryItem, MealSlot, CriticVerdict
from shopper.validators import (
    validate_fridge_inventory_consistency,
    validate_grocery_aggregation,
    validate_grocery_fridge_diff,
    validate_grocery_list,
    validate_grocery_traceability,
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
            message="Reviewing grocery coverage, aggregation, fridge diffing, and traceability.",
        )

        context = await self.context_assembler.build_context("shopping_critic", state)
        meals = [MealSlot.model_validate(item) for item in state["selected_meals"]]
        grocery_list = [GroceryItem.model_validate(item) for item in state.get("grocery_list", [])]
        fridge_inventory = [FridgeItemSnapshot.model_validate(item) for item in state.get("fridge_inventory", [])]

        findings = dedupe_findings(
            [
                *build_findings("S_COVERAGE", validate_grocery_list(meals, grocery_list), severity="issue"),
                *build_findings("S_AGGREGATION", validate_grocery_aggregation(meals, grocery_list), severity="issue"),
                *build_findings(
                    "S_FRIDGE_DIFF",
                    validate_grocery_fridge_diff(meals, grocery_list, fridge_inventory),
                    severity="issue",
                ),
                *build_findings(
                    "S_FRIDGE_DIFF",
                    validate_fridge_inventory_consistency(grocery_list, fridge_inventory),
                    severity="issue",
                ),
                *build_findings("S_TRACEABILITY", validate_grocery_traceability(meals, grocery_list), severity="issue"),
            ]
        )

        llm_assessment = await self._llm_review(context.payload, meals, grocery_list, fridge_inventory)
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
        if "S_COVERAGE" in codes:
            instructions.append("Rebuild the grocery list so every recipe ingredient is represented exactly once.")
        if "S_AGGREGATION" in codes:
            instructions.append("Re-aggregate duplicated or over-counted grocery items across recipes before finalizing the list.")
        if "S_FRIDGE_DIFF" in codes:
            instructions.append("Re-diff the grocery list against fridge inventory and recompute already-have and shopping quantities.")
        if "S_TRACEABILITY" in codes:
            instructions.append("Attach the correct source recipe ids to every grocery item for traceability.")
        return instructions
