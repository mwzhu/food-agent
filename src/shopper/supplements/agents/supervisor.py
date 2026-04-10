from __future__ import annotations

from typing import Any, Dict

from shopper.supplements.schemas import SupplementCriticVerdict


async def supplement_supervisor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    return {"current_node": "supervisor"}


def route_from_supervisor(state: Dict[str, Any]) -> str:
    status = state.get("status")
    if status in {"awaiting_approval", "completed", "failed"}:
        return "end"

    current_phase = state.get("current_phase", "memory")
    assert current_phase in {"memory", "discovery", "analysis", "checkout"}

    if current_phase == "checkout":
        return "checkout_subgraph"
    if current_phase == "analysis":
        critic_verdict = state.get("critic_verdict") or {}
        if critic_verdict.get("decision") == "failed":
            return "analysis_subgraph"
        if state.get("recommended_stack"):
            return "critic_subgraph"
        return "analysis_subgraph"
    if current_phase == "discovery":
        return "discovery_subgraph"
    return "load_memory"


def route_from_critic(state: Dict[str, Any], max_replans: int = 0) -> str:
    verdict = SupplementCriticVerdict.model_validate(state["critic_verdict"])
    if verdict.decision == "passed":
        return "checkout_subgraph"
    if verdict.decision == "failed" and state.get("replan_count", 0) < max_replans:
        return "analysis_subgraph"
    return "end"
