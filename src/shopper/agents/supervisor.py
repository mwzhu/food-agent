from __future__ import annotations

from typing import Any, Dict, Literal

from shopper.schemas import CriticVerdict


async def supervisor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    return {"current_node": "supervisor"}


def route_from_supervisor(state: Dict[str, Any]) -> str:
    if state.get("replan_count", 0) > 0:
        return "planning_subgraph"
    return "load_memory"


def route_from_critic(state: Dict[str, Any], max_replans: int = 3) -> str:
    verdict = CriticVerdict.model_validate(state["critic_verdict"])
    current_phase = state.get("current_phase", "planning")
    assert current_phase in ("planning", "shopping")
    phase: Literal["planning", "shopping"] = current_phase
    if phase == "shopping":
        return "end"
    if verdict.passed:
        return "shopping_subgraph"
    if state["replan_count"] >= max_replans:
        return "end"
    return "planning_subgraph"
