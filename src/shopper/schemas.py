from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProfileFacts(BaseModel):
    age: int = 30
    sex: Literal["female", "male", "other"] = "other"
    height_cm: float = 170
    weight_kg: float = 70
    activity_level: Literal["low", "moderate", "high"] = "moderate"
    goal: Literal["cut", "maintain", "bulk"] = "maintain"
    dietary_restrictions: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    household_size: int = 1
    weekday_time_limit_minutes: int = 30
    preferred_stores: list[str] = Field(default_factory=lambda: ["walmart"])


class PantryItem(BaseModel):
    name: str
    quantity: float = 1
    unit: str = "unit"
    category: str | None = None


class NutritionTargets(BaseModel):
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    fiber_g: int
    notes: str


class RecipeCandidate(BaseModel):
    recipe_id: str
    name: str
    tags: list[str] = Field(default_factory=list)
    prep_time_minutes: int
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    ingredients: list[PantryItem] = Field(default_factory=list)


class MealPlan(BaseModel):
    recipe_ids: list[str]
    recipes: list[RecipeCandidate]
    rationale: str


class GroceryDemandItem(BaseModel):
    name: str
    quantity: float
    unit: str
    category: str
    already_have: bool = False


class StoreQuote(BaseModel):
    store: str
    item_name: str
    unit_price: float
    available: bool = True


class BasketPlanItem(BaseModel):
    item_name: str
    store: str
    quantity: float
    unit: str
    estimated_cost: float
    buy_online: bool


class BasketPlan(BaseModel):
    items: list[BasketPlanItem]
    estimated_total: float
    rationale: str


class VerifierResult(BaseModel):
    stage: str
    passed: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    run_id: str
    reason: str
    basket_plan: BasketPlan


class CheckoutResult(BaseModel):
    status: Literal["approved", "rejected", "completed", "manual_review"]
    confirmation_id: str | None = None
    message: str


class MemoryEvent(BaseModel):
    user_id: str
    namespace: str
    content: str
    source_run_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PreferenceSummary(BaseModel):
    likes: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    preferred_tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RunInput(BaseModel):
    user_id: str
    profile: ProfileFacts
    budget_weekly: float = 150.0
    schedule_summary: str = "Standard week with weekday dinners and flexible lunch."
    pantry_snapshot: list[PantryItem] = Field(default_factory=list)
    require_approval: bool = True


class HumanEdit(BaseModel):
    notes: str | None = None
    remove_items: list[str] = Field(default_factory=list)


class ResumeRequest(BaseModel):
    approved: bool
    human_edit: HumanEdit | None = None


class FeedbackRequest(BaseModel):
    user_id: str
    run_id: str | None = None
    namespace: str = "meal_feedback"
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class BootstrapSessionRequest(BaseModel):
    user_id: str
    profile_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunResponse(BaseModel):
    run_id: str
    status: str
    current_stage: str
    artifacts: dict[str, Any] = Field(default_factory=dict)
    pending_interrupt: dict[str, Any] | None = None
    verifier_results: list[VerifierResult] = Field(default_factory=list)
    trace_metadata: dict[str, Any] = Field(default_factory=dict)

