from __future__ import annotations

import operator
from typing import Any, Annotated, Dict, List, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages

from shopper.schemas import MealType, PhaseName, PhaseStatus, RunLifecycleStatus


class NutritionPlanState(TypedDict):
    tdee: int
    daily_calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    fiber_g: int
    goal: str
    applied_restrictions: List[str]
    notes: str


class MealSlotState(TypedDict):
    day: str
    meal_type: MealType
    recipe_id: str
    recipe_name: str
    cuisine: str
    prep_time_min: int
    serving_multiplier: float
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    tags: List[str]
    macro_fit_score: float
    recipe: Dict[str, Any]


class CriticVerdictState(TypedDict):
    passed: bool
    issues: List[str]
    warnings: List[str]
    repair_instructions: List[str]


class PhaseStatusesState(TypedDict):
    memory: PhaseStatus
    planning: PhaseStatus
    shopping: PhaseStatus
    checkout: PhaseStatus


class PlannerState(TypedDict, total=False):
    run_id: str
    user_id: str
    user_profile: Dict[str, Any]
    nutrition_plan: NutritionPlanState
    selected_meals: List[MealSlotState]
    user_preferences_learned: Dict[str, Any]
    retrieved_memories: List[Dict[str, Any]]
    critic_verdict: CriticVerdictState
    repair_instructions: List[str]
    blocked_recipe_ids: List[str]
    avoid_cuisines: List[str]
    context_metadata: Annotated[List[Dict[str, Any]], operator.add]
    status: RunLifecycleStatus
    current_node: str
    current_phase: PhaseName
    phase_statuses: PhaseStatusesState
    replan_count: int
    latest_error: str
    trace_metadata: Dict[str, Any]


class PlanningSubgraphState(TypedDict, total=False):
    run_id: str
    user_id: str
    user_profile: Dict[str, Any]
    nutrition_plan: NutritionPlanState
    selected_meals: List[MealSlotState]
    user_preferences_learned: Dict[str, Any]
    retrieved_memories: List[Dict[str, Any]]
    critic_verdict: CriticVerdictState
    repair_instructions: List[str]
    blocked_recipe_ids: List[str]
    avoid_cuisines: List[str]
    replan_count: int
    context_metadata: Annotated[List[Dict[str, Any]], operator.add]
    messages: Annotated[List[BaseMessage], add_messages]
