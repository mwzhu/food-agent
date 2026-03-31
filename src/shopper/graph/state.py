from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class RunState(TypedDict, total=False):
    run_id: str
    user_id: str
    profile: Dict[str, Any]
    budget_weekly: float
    schedule_summary: str
    pantry_snapshot: List[Dict[str, Any]]
    approval_required: bool
    canonical_memory: Dict[str, Any]
    episodic_memory: List[str]
    context_logs: List[Dict[str, Any]]
    nutrition_targets: Dict[str, Any]
    candidate_recipes: List[Dict[str, Any]]
    meal_plan: Dict[str, Any]
    grocery_demand: List[Dict[str, Any]]
    quotes: List[Dict[str, Any]]
    basket_plan: Dict[str, Any]
    browser_state: Dict[str, Any]
    pending_interrupt: Optional[Dict[str, Any]]
    verifier_results: List[Dict[str, Any]]
    current_stage: str
    status: str
    trace_metadata: Dict[str, Any]
    error_message: Optional[str]
