from __future__ import annotations

import operator
from typing import Any, Annotated, Dict, List, Optional, TypedDict

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
    findings: List[Dict[str, Any]]


class GroceryItemState(TypedDict):
    name: str
    quantity: float
    unit: Optional[str]
    category: str
    already_have: bool
    shopping_quantity: float
    quantity_in_fridge: float
    source_recipe_ids: List[str]
    best_store: Optional[str]
    best_price: Optional[float]
    buy_online: Optional[bool]


class StoreQuoteState(TypedDict):
    store: str
    item_name: str
    requested_quantity: float
    requested_unit: Optional[str]
    price: float
    unit_price: float
    in_stock: bool
    delivery_fee: float
    min_order: float


class StoreSummaryState(TypedDict):
    store: str
    item_count: int
    available_item_count: int
    subtotal: float
    delivery_fee: float
    total: float
    min_order: float
    all_items_available: bool
    meets_min_order: bool


class PurchaseOrderItemState(TypedDict):
    name: str
    quantity: float
    unit: Optional[str]
    category: str
    source_recipe_ids: List[str]
    price: float
    unit_price: float


class PurchaseOrderState(TypedDict):
    store: str
    items: List[PurchaseOrderItemState]
    subtotal: float
    delivery_fee: float
    total_cost: float
    channel: str
    status: str


class BudgetSummaryState(TypedDict):
    budget: float
    total_cost: float
    overage: float
    within_budget: bool
    utilization: float


class FridgeItemState(TypedDict):
    item_id: int
    user_id: str
    name: str
    quantity: float
    unit: Optional[str]
    category: str
    expiry_date: Optional[str]


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
    grocery_list: List[GroceryItemState]
    store_quotes: List[StoreQuoteState]
    store_summaries: List[StoreSummaryState]
    purchase_orders: List[PurchaseOrderState]
    budget_summary: BudgetSummaryState
    fridge_inventory: List[FridgeItemState]
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
    replan_reason: str
    price_strategy: str
    price_rationale: str
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


class ShoppingSubgraphState(TypedDict, total=False):
    run_id: str
    user_id: str
    user_profile: Dict[str, Any]
    selected_meals: List[MealSlotState]
    grocery_list: List[GroceryItemState]
    store_quotes: List[StoreQuoteState]
    store_summaries: List[StoreSummaryState]
    purchase_orders: List[PurchaseOrderState]
    budget_summary: BudgetSummaryState
    fridge_inventory: List[FridgeItemState]
    replan_reason: str
    price_strategy: str
    price_rationale: str
    context_metadata: Annotated[List[Dict[str, Any]], operator.add]
