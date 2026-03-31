from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class NutritionPlan(BaseModel):
    tdee: int
    daily_calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    fiber_g: int
    goal: Literal["cut", "maintain", "bulk"]
    applied_restrictions: List[str] = Field(default_factory=list)
    notes: str = ""


class MealSlot(BaseModel):
    day: str
    meal_type: Literal["breakfast", "lunch", "dinner"]
    recipe_id: str
    recipe_name: str
    prep_time_min: int
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int


class ContextMetadata(BaseModel):
    node_name: str
    tokens_used: int
    token_budget: int
    fields_included: List[str] = Field(default_factory=list)
    fields_dropped: List[str] = Field(default_factory=list)
    retrieved_memory_ids: List[str] = Field(default_factory=list)


class PlannerStateSnapshot(BaseModel):
    run_id: str
    user_id: str
    user_profile: Dict[str, Any]
    nutrition_plan: Optional[NutritionPlan] = None
    selected_meals: List[MealSlot] = Field(default_factory=list)
    context_metadata: List[ContextMetadata] = Field(default_factory=list)
    status: Literal["pending", "completed"] = "pending"
    current_node: Literal["created", "supervisor", "planning_subgraph"] = "created"
    trace_metadata: Dict[str, Any] = Field(default_factory=dict)
