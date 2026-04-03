from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from shopper.schemas.grocery import GroceryItem
from shopper.schemas.inventory import FridgeItemSnapshot
from shopper.schemas.user import UserProfileBase


MealType = Literal["breakfast", "lunch", "dinner", "snack"]
RunLifecycleStatus = Literal["pending", "running", "completed", "failed"]
PhaseName = Literal["memory", "planning", "shopping", "checkout"]
PhaseStatus = Literal["pending", "running", "completed", "locked", "failed"]
RunEventType = Literal[
    "phase_started",
    "phase_completed",
    "node_entered",
    "node_completed",
    "run_completed",
    "error",
]


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


class RecipeIngredient(BaseModel):
    name: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    note: str = ""


class RecipeRecord(BaseModel):
    recipe_id: str
    name: str
    cuisine: str
    meal_types: List[MealType] = Field(default_factory=list)
    ingredients: List[RecipeIngredient] = Field(default_factory=list)
    prep_time_min: int
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    tags: List[str] = Field(default_factory=list)
    instructions: List[str] = Field(default_factory=list)
    source_url: Optional[str] = None


class PreferenceSummary(BaseModel):
    preferred_cuisines: List[str] = Field(default_factory=list)
    avoided_ingredients: List[str] = Field(default_factory=list)
    preferred_meal_types: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class MealSlot(BaseModel):
    day: str
    meal_type: MealType
    recipe_id: str
    recipe_name: str
    cuisine: str = ""
    prep_time_min: int
    serving_multiplier: float = 1.0
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    tags: List[str] = Field(default_factory=list)
    macro_fit_score: float = 0.0
    recipe: Optional[RecipeRecord] = None


class CriticVerdict(BaseModel):
    passed: bool
    issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    repair_instructions: List[str] = Field(default_factory=list)


class RunEvent(BaseModel):
    event_id: str
    run_id: str
    event_type: RunEventType
    message: str
    phase: Optional[PhaseName] = None
    node_name: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: Dict[str, Any] = Field(default_factory=dict)


class ContextMetadata(BaseModel):
    node_name: str
    tokens_used: int
    token_budget: int
    fields_included: List[str] = Field(default_factory=list)
    fields_dropped: List[str] = Field(default_factory=list)
    retrieved_memory_ids: List[str] = Field(default_factory=list)


class PhaseStatuses(BaseModel):
    memory: PhaseStatus = "pending"
    planning: PhaseStatus = "pending"
    shopping: PhaseStatus = "locked"
    checkout: PhaseStatus = "locked"


class TraceMetadata(BaseModel):
    kind: Optional[str] = None
    project: Optional[str] = None
    trace_id: Optional[str] = None
    source: Optional[str] = None


class PlannerStateSnapshot(BaseModel):
    run_id: str
    user_id: str
    user_profile: UserProfileBase
    nutrition_plan: Optional[NutritionPlan] = None
    selected_meals: List[MealSlot] = Field(default_factory=list)
    grocery_list: List[GroceryItem] = Field(default_factory=list)
    fridge_inventory: List[FridgeItemSnapshot] = Field(default_factory=list)
    user_preferences_learned: PreferenceSummary = Field(default_factory=PreferenceSummary)
    retrieved_memories: List[Dict[str, Any]] = Field(default_factory=list)
    critic_verdict: Optional[CriticVerdict] = None
    repair_instructions: List[str] = Field(default_factory=list)
    blocked_recipe_ids: List[str] = Field(default_factory=list)
    avoid_cuisines: List[str] = Field(default_factory=list)
    context_metadata: List[ContextMetadata] = Field(default_factory=list)
    status: RunLifecycleStatus = "pending"
    current_node: str = "created"
    current_phase: Optional[PhaseName] = None
    phase_statuses: PhaseStatuses = Field(default_factory=PhaseStatuses)
    replan_count: int = 0
    latest_error: Optional[str] = None
    trace_metadata: TraceMetadata = Field(default_factory=TraceMetadata)

    @classmethod
    def starting(
        cls,
        *,
        run_id: str,
        user_id: str,
        user_profile: Union[UserProfileBase, Dict[str, Any]],
    ) -> "PlannerStateSnapshot":
        return cls(
            run_id=run_id,
            user_id=user_id,
            user_profile=user_profile,
            status="running",
            current_phase="memory",
            phase_statuses=PhaseStatuses(memory="running"),
        )

    def as_failed(self, message: str) -> "PlannerStateSnapshot":
        phase = self.current_phase or "planning"
        phase_statuses = self.phase_statuses.model_copy(deep=True)
        if phase == "memory":
            phase_statuses.memory = "failed"
        elif phase == "planning":
            phase_statuses.memory = "completed"
            phase_statuses.planning = "failed"
        elif phase == "shopping":
            phase_statuses.memory = "completed"
            phase_statuses.planning = "completed"
            phase_statuses.shopping = "failed"
        else:
            phase_statuses.checkout = "failed"
        return self.model_copy(
            update={
                "status": "failed",
                "latest_error": message,
                "current_phase": phase,
                "current_node": "error",
                "phase_statuses": phase_statuses,
            }
        )
