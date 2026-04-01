from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from shopper.agents.events import emit_run_event
from shopper.agents.llm import invoke_structured
from shopper.schemas import ContextMetadata, CriticVerdict, MealSlot


PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "substitution.md"
RECIPE_ID_PATTERN = re.compile(r"\b[a-z0-9]+(?:-[a-z0-9]+)+\b")


class SubstitutionDecision(BaseModel):
    blocked_recipe_ids: List[str] = Field(default_factory=list)
    avoid_cuisines: List[str] = Field(default_factory=list)
    repair_instructions: List[str] = Field(default_factory=list)
    rationale: str = ""


@dataclass
class SubstitutionNode:
    chat_model: Optional[Any] = None

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_entered",
            phase="planning",
            node_name="substitution",
            message="Preparing a constrained replan after critic feedback.",
        )

        verdict = CriticVerdict.model_validate(state["critic_verdict"])
        meals = [MealSlot.model_validate(item) for item in state["selected_meals"]]
        prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
        decision = await self._plan_constraints(prompt=prompt, verdict=verdict, meals=meals)
        blocked_recipe_ids = sorted(
            set(state["blocked_recipe_ids"])
            | self._blocked_recipe_ids(verdict, meals)
            | set(decision.blocked_recipe_ids)
        )
        avoid_cuisines = sorted(
            set(state["avoid_cuisines"])
            | self._avoid_cuisines(verdict)
            | {cuisine.lower() for cuisine in decision.avoid_cuisines}
        )
        repair_instructions = list(
            dict.fromkeys(
                list(state["repair_instructions"])
                + verdict.repair_instructions
                + decision.repair_instructions
            )
        )
        repair_instructions.append("Apply stricter novelty rules to avoid repeating recently rejected meals.")

        replan_count = state["replan_count"] + 1
        metadata = ContextMetadata(
            node_name="substitution",
            tokens_used=max(1, len(prompt) // 4),
            token_budget=1400,
            fields_included=["critic_verdict", "selected_meals", "repair_instructions"],
            fields_dropped=[],
            retrieved_memory_ids=[],
        )

        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_completed",
            phase="planning",
            node_name="substitution",
            message="Replan attempt {count} will avoid {recipes} flagged recipes.".format(
                count=replan_count,
                recipes=len(blocked_recipe_ids),
            ),
            data={
                "replan_count": replan_count,
                "blocked_recipe_ids": blocked_recipe_ids,
                "avoid_cuisines": avoid_cuisines,
            },
        )

        return {
            "replan_count": replan_count,
            "repair_instructions": repair_instructions,
            "blocked_recipe_ids": blocked_recipe_ids,
            "avoid_cuisines": avoid_cuisines,
            "context_metadata": [metadata.model_dump(mode="json")],
            "messages": [
                AIMessage(
                    content="Substitution constraints updated for replanning with {mode}.".format(
                        mode="LLM support" if self.chat_model is not None else "deterministic fallback"
                    )
                )
            ],
            "current_node": "substitution",
            "current_phase": "planning",
            "status": "running",
            "phase_statuses": {
                "memory": "completed",
                "planning": "running",
                "shopping": "locked",
                "checkout": "locked",
            },
        }

    async def _plan_constraints(
        self,
        prompt: str,
        verdict: CriticVerdict,
        meals: List[MealSlot],
    ) -> SubstitutionDecision:
        if self.chat_model is None:
            return SubstitutionDecision()

        payload = {
            "critic_verdict": verdict.model_dump(mode="json"),
            "selected_meals": [self._meal_summary(meal) for meal in meals],
        }
        decision = await invoke_structured(
            self.chat_model,
            SubstitutionDecision,
            [
                SystemMessage(content=prompt),
                HumanMessage(content=json.dumps(payload, indent=2, ensure_ascii=True)),
            ],
        )
        return decision or SubstitutionDecision()

    def _meal_summary(self, meal: MealSlot) -> Dict[str, Any]:
        return {
            "day": meal.day,
            "meal_type": meal.meal_type,
            "recipe_id": meal.recipe_id,
            "recipe_name": meal.recipe_name,
            "cuisine": meal.cuisine,
            "macro_fit_score": meal.macro_fit_score,
        }

    def _blocked_recipe_ids(self, verdict: CriticVerdict, meals: List[MealSlot]) -> Set[str]:
        blocked: Set[str] = set()
        for issue in verdict.issues:
            blocked.update(RECIPE_ID_PATTERN.findall(issue.lower()))

        if not blocked and meals:
            blocked.add(min(meals, key=lambda meal: meal.macro_fit_score).recipe_id)

        return blocked

    def _avoid_cuisines(self, verdict: CriticVerdict) -> Set[str]:
        cuisines: Set[str] = set()
        for warning in verdict.warnings:
            lowered = warning.lower()
            if "cuisine repeat detected for " in lowered:
                cuisines.add(lowered.split("cuisine repeat detected for ", 1)[1].split(" around ", 1)[0].strip())
        return cuisines
