from __future__ import annotations

import operator
from typing import Any, Annotated, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages

from shopper.supplements.schemas.run import (
    SupplementPhaseName,
    SupplementPhaseStatus,
    SupplementRunLifecycleStatus,
)


class SupplementNeedState(TypedDict):
    category: str
    goal: str
    rationale: str
    search_queries: List[str]
    priority: int


class SupplementProductVariantState(TypedDict):
    variant_id: str
    title: str
    price: Optional[float]
    currency: str
    available: bool
    image_url: Optional[str]


class SupplementProductState(TypedDict):
    store_domain: str
    product_id: str
    title: str
    description: str
    url: str
    image_url: Optional[str]
    image_alt_text: Optional[str]
    product_type: str
    tags: List[str]
    price_range: Dict[str, Any]
    variants: List[SupplementProductVariantState]


class StoreSearchResultState(TypedDict):
    store_domain: str
    query: str
    products: List[SupplementProductState]


class CategoryDiscoveryResultState(TypedDict):
    category: str
    goal: str
    search_queries: List[str]
    store_results: List[StoreSearchResultState]


class IngredientAnalysisState(TypedDict):
    primary_ingredients: List[str]
    dosage_summary: str
    bioavailability_notes: List[str]
    allergens: List[str]
    serving_size: Optional[str]
    servings_per_container: Optional[float]
    price_per_serving: Optional[float]
    notes: List[str]


class ComparedProductState(TypedDict):
    product: SupplementProductState
    ingredient_analysis: IngredientAnalysisState
    rank: int
    score: Optional[float]
    rationale: str
    pros: List[str]
    cons: List[str]
    warnings: List[str]
    monthly_cost: Optional[float]


class ProductComparisonState(TypedDict):
    category: str
    goal: str
    summary: str
    ranked_products: List[ComparedProductState]
    top_pick_product_id: Optional[str]
    top_pick_store_domain: Optional[str]


class StackItemState(TypedDict):
    category: str
    goal: str
    product: SupplementProductState
    quantity: int
    dosage: str
    cadence: str
    monthly_cost: Optional[float]
    rationale: str
    cautions: List[str]


class SupplementStackState(TypedDict):
    summary: str
    items: List[StackItemState]
    total_monthly_cost: Optional[float]
    currency: str
    within_budget: Optional[bool]
    notes: List[str]
    warnings: List[str]


class SupplementCriticFindingState(TypedDict):
    concern: str
    severity: str
    message: str


class SupplementCriticVerdictState(TypedDict):
    decision: str
    summary: str
    issues: List[str]
    warnings: List[str]
    findings: List[SupplementCriticFindingState]
    manual_review_reason: Optional[str]


class StoreCartLineState(TypedDict):
    line_id: str
    product_id: str
    product_title: str
    variant_id: str
    variant_title: str
    quantity: int
    subtotal_amount: Optional[float]
    total_amount: Optional[float]
    currency: Optional[str]


class StoreCartState(TypedDict):
    store_domain: str
    cart_id: Optional[str]
    checkout_url: Optional[str]
    total_quantity: int
    subtotal_amount: Optional[float]
    total_amount: Optional[float]
    currency: Optional[str]
    lines: List[StoreCartLineState]
    errors: List[Dict[str, Any]]
    instructions: Optional[str]


class SupplementPhaseStatusesState(TypedDict):
    memory: SupplementPhaseStatus
    discovery: SupplementPhaseStatus
    analysis: SupplementPhaseStatus
    checkout: SupplementPhaseStatus


class SupplementRunState(TypedDict, total=False):
    run_id: str
    user_id: str
    health_profile: Dict[str, Any]
    identified_needs: List[SupplementNeedState]
    discovery_results: List[CategoryDiscoveryResultState]
    product_comparisons: List[ProductComparisonState]
    recommended_stack: SupplementStackState
    critic_verdict: SupplementCriticVerdictState
    store_carts: List[StoreCartState]
    approved_store_domains: List[str]
    status: SupplementRunLifecycleStatus
    current_node: str
    current_phase: SupplementPhaseName
    phase_statuses: SupplementPhaseStatusesState
    replan_count: int
    latest_error: str
    trace_metadata: Dict[str, Any]
    context_metadata: Annotated[List[Dict[str, Any]], operator.add]


class DiscoverySubgraphState(TypedDict, total=False):
    run_id: str
    user_id: str
    health_profile: Dict[str, Any]
    identified_needs: List[SupplementNeedState]
    discovery_results: List[CategoryDiscoveryResultState]
    context_metadata: Annotated[List[Dict[str, Any]], operator.add]
    messages: Annotated[List[BaseMessage], add_messages]


class AnalysisSubgraphState(TypedDict, total=False):
    run_id: str
    user_id: str
    health_profile: Dict[str, Any]
    identified_needs: List[SupplementNeedState]
    discovery_results: List[CategoryDiscoveryResultState]
    product_comparisons: List[ProductComparisonState]
    recommended_stack: SupplementStackState
    replan_count: int
    context_metadata: Annotated[List[Dict[str, Any]], operator.add]
    messages: Annotated[List[BaseMessage], add_messages]


class CriticSubgraphState(TypedDict, total=False):
    run_id: str
    user_id: str
    health_profile: Dict[str, Any]
    product_comparisons: List[ProductComparisonState]
    recommended_stack: SupplementStackState
    critic_verdict: SupplementCriticVerdictState
    context_metadata: Annotated[List[Dict[str, Any]], operator.add]
    messages: Annotated[List[BaseMessage], add_messages]


class CheckoutSubgraphState(TypedDict, total=False):
    run_id: str
    user_id: str
    recommended_stack: SupplementStackState
    store_carts: List[StoreCartState]
    approved_store_domains: List[str]
    status: SupplementRunLifecycleStatus
    current_node: str
    current_phase: SupplementPhaseName
    phase_statuses: SupplementPhaseStatusesState
    latest_error: str
    context_metadata: Annotated[List[Dict[str, Any]], operator.add]
