from __future__ import annotations

import operator
from typing import Any, Annotated, Dict, List, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


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
    meal_type: str
    recipe_id: str
    recipe_name: str
    prep_time_min: int
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int


class PlannerState(TypedDict, total=False):
    run_id: str
    user_id: str
    user_profile: Dict[str, Any]
    nutrition_plan: NutritionPlanState
    selected_meals: List[MealSlotState]
    context_metadata: Annotated[List[Dict[str, Any]], operator.add]
    status: Literal["pending", "completed"]
    current_node: Literal["created", "supervisor", "planning_subgraph"]
    trace_metadata: Dict[str, Any]


class PlanningSubgraphState(TypedDict, total=False):
    run_id: str
    user_id: str
    user_profile: Dict[str, Any]
    nutrition_plan: NutritionPlanState
    selected_meals: List[MealSlotState]
    context_metadata: Annotated[List[Dict[str, Any]], operator.add]
    messages: Annotated[List[BaseMessage], add_messages]
