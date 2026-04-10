from __future__ import annotations

import json
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from shopper.agents.llm import invoke_structured
from shopper.supplements.agents.nodes.common import estimate_monthly_cost, product_currency, product_price
from shopper.supplements.events import emit_supplement_event
from shopper.supplements.schemas import HealthProfile, ProductComparison, StackItem, SupplementNeed, SupplementStack


SYSTEM_PROMPT = """
You build a practical supplement shopping stack from ranked category comparisons.
Use only the provided candidates and stay within budget when possible.
Favor fewer high-confidence products over a crowded stack.
Keep quantity values realistic for a first monthly purchase.
""".strip()


class StackSelectionDecision(BaseModel):
    category: str
    store_domain: str
    product_id: str
    quantity: int = Field(default=1, ge=1)
    dosage: str = ""
    cadence: str = ""
    monthly_cost: Optional[float] = None
    rationale: str = ""
    cautions: list[str] = Field(default_factory=list)


class StackPlanDecision(BaseModel):
    summary: str = ""
    items: list[StackSelectionDecision] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


async def stack_builder(
    state: dict[str, Any],
    *,
    chat_model: Optional[Any] = None,
) -> dict[str, Any]:
    run_id = state["run_id"]
    await emit_supplement_event(
        run_id=run_id,
        event_type="node_entered",
        phase="analysis",
        node_name="stack_builder",
        message="Building a budget-aware supplement stack from ranked product comparisons.",
    )

    health_profile = HealthProfile.model_validate(state["health_profile"])
    identified_needs = [SupplementNeed.model_validate(item) for item in state.get("identified_needs", [])]
    comparisons = [ProductComparison.model_validate(item) for item in state.get("product_comparisons", [])]

    stack = await _llm_stack(
        health_profile=health_profile,
        identified_needs=identified_needs,
        comparisons=comparisons,
        chat_model=chat_model,
    )
    if stack is None:
        stack = _fallback_stack(
            health_profile=health_profile,
            identified_needs=identified_needs,
            comparisons=comparisons,
        )

    await emit_supplement_event(
        run_id=run_id,
        event_type="node_completed",
        phase="analysis",
        node_name="stack_builder",
        message="Built a supplement stack with {count} items.".format(count=len(stack.items)),
        data={
            "item_count": len(stack.items),
            "total_monthly_cost": stack.total_monthly_cost,
            "within_budget": stack.within_budget,
        },
    )

    return {
        "recommended_stack": stack.model_dump(mode="json"),
        "messages": [
            AIMessage(
                content="Built a supplement stack with {count} items and estimated monthly cost ${cost}.".format(
                    count=len(stack.items),
                    cost="{amount:.2f}".format(amount=stack.total_monthly_cost or 0.0),
                )
            )
        ],
    }


async def _llm_stack(
    *,
    health_profile: HealthProfile,
    identified_needs: list[SupplementNeed],
    comparisons: list[ProductComparison],
    chat_model: Optional[Any],
) -> Optional[SupplementStack]:
    if chat_model is None or not comparisons:
        return None

    evidence = {
        "health_profile": health_profile.model_dump(mode="json"),
        "identified_needs": [need.model_dump(mode="json") for need in identified_needs],
        "comparisons": [
            {
                "category": comparison.category,
                "goal": comparison.goal,
                "summary": comparison.summary,
                "ranked_products": [
                    {
                        "rank": product.rank,
                        "store_domain": product.product.store_domain,
                        "product_id": product.product.product_id,
                        "title": product.product.title,
                        "price": product_price(product.product),
                        "monthly_cost": product.monthly_cost,
                        "rationale": product.rationale,
                        "warnings": product.warnings,
                        "ingredient_analysis": product.ingredient_analysis.model_dump(mode="json"),
                    }
                    for product in comparison.ranked_products[:3]
                ],
            }
            for comparison in comparisons
        ],
    }

    try:
        response = await invoke_structured(
            chat_model,
            StackPlanDecision,
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=json.dumps(evidence, indent=2, ensure_ascii=True)),
            ],
        )
    except Exception:
        return None

    if response is None or not response.items:
        return None

    selection = _selection_from_decision(response, comparisons)
    if not selection:
        return None

    return _materialize_stack(
        health_profile=health_profile,
        identified_needs=identified_needs,
        comparisons=comparisons,
        selection=selection,
        decision=response,
    )


def _fallback_stack(
    *,
    health_profile: HealthProfile,
    identified_needs: list[SupplementNeed],
    comparisons: list[ProductComparison],
) -> SupplementStack:
    selection = {
        comparison.category: 0
        for comparison in comparisons
        if comparison.ranked_products
    }
    return _materialize_stack(
        health_profile=health_profile,
        identified_needs=identified_needs,
        comparisons=comparisons,
        selection=selection,
        decision=None,
    )


def _selection_from_decision(
    decision: StackPlanDecision,
    comparisons: list[ProductComparison],
) -> dict[str, int]:
    selection: dict[str, int] = {}
    for item in decision.items:
        matching_comparison = next(
            (comparison for comparison in comparisons if comparison.category.lower() == item.category.lower()),
            None,
        )
        if matching_comparison is None:
            continue
        for index, compared_product in enumerate(matching_comparison.ranked_products):
            if (
                compared_product.product.store_domain == item.store_domain
                and compared_product.product.product_id == item.product_id
            ):
                selection[matching_comparison.category] = index
                break
    return selection


def _materialize_stack(
    *,
    health_profile: HealthProfile,
    identified_needs: list[SupplementNeed],
    comparisons: list[ProductComparison],
    selection: dict[str, int],
    decision: Optional[StackPlanDecision],
) -> SupplementStack:
    priority_by_category = {need.category.lower(): need.priority for need in identified_needs}
    adjusted_selection, budget_notes = _apply_budget_controls(
        selection=selection,
        comparisons=comparisons,
        priority_by_category=priority_by_category,
        budget=health_profile.monthly_budget,
    )

    decision_lookup = {
        (item.category.lower(), item.store_domain, item.product_id): item
        for item in (decision.items if decision is not None else [])
    }

    items: list[StackItem] = []
    total_cost = 0.0
    has_cost = False
    currency = "USD"
    warnings: list[str] = []

    for comparison in comparisons:
        selected_index = adjusted_selection.get(comparison.category)
        if selected_index is None or selected_index >= len(comparison.ranked_products):
            continue
        compared_product = comparison.ranked_products[selected_index]
        choice_key = (
            comparison.category.lower(),
            compared_product.product.store_domain,
            compared_product.product.product_id,
        )
        decision_item = decision_lookup.get(choice_key)

        monthly_cost = (
            decision_item.monthly_cost
            if decision_item is not None and decision_item.monthly_cost is not None
            else _option_cost(compared_product)
        )
        quantity = decision_item.quantity if decision_item is not None else 1
        if monthly_cost is not None:
            monthly_cost = round(monthly_cost * quantity, 2)
            total_cost += monthly_cost
            has_cost = True
        currency = product_currency(compared_product.product)
        cautions = _dedupe_strings(
            (decision_item.cautions if decision_item is not None else [])
            + compared_product.warnings
        )
        warnings.extend(cautions)
        items.append(
            StackItem(
                category=comparison.category,
                goal=comparison.goal,
                product=compared_product.product,
                quantity=quantity,
                dosage=(
                    decision_item.dosage
                    if decision_item is not None and decision_item.dosage
                    else _default_dosage(comparison.category, compared_product)
                ),
                cadence=(
                    decision_item.cadence
                    if decision_item is not None and decision_item.cadence
                    else _default_cadence(comparison.category)
                ),
                monthly_cost=monthly_cost,
                rationale=(
                    decision_item.rationale
                    if decision_item is not None and decision_item.rationale
                    else compared_product.rationale
                ),
                cautions=cautions,
            )
        )

    total_monthly_cost = round(total_cost, 2) if has_cost else None
    within_budget = (
        total_monthly_cost <= health_profile.monthly_budget
        if total_monthly_cost is not None
        else None
    )

    notes = _dedupe_strings((decision.notes if decision is not None else []) + budget_notes)
    warnings = _dedupe_strings((decision.warnings if decision is not None else []) + warnings)
    if within_budget is False:
        warnings.append(
            "Estimated total of ${total:.2f} is above the ${budget:.2f} monthly budget.".format(
                total=total_monthly_cost or 0.0,
                budget=health_profile.monthly_budget,
            )
        )

    summary = (
        decision.summary
        if decision is not None and decision.summary
        else _fallback_summary(items, total_monthly_cost, health_profile.monthly_budget)
    )
    return SupplementStack(
        summary=summary,
        items=items,
        total_monthly_cost=total_monthly_cost,
        currency=currency,
        within_budget=within_budget,
        notes=notes,
        warnings=warnings,
    )


def _apply_budget_controls(
    *,
    selection: dict[str, int],
    comparisons: list[ProductComparison],
    priority_by_category: dict[str, int],
    budget: float,
) -> tuple[dict[str, int], list[str]]:
    adjusted = dict(selection)
    notes: list[str] = []
    total = _selection_total(adjusted, comparisons)
    if total is None or total <= budget:
        return adjusted, notes

    for comparison in sorted(
        comparisons,
        key=lambda item: (priority_by_category.get(item.category.lower(), 999), item.category.lower()),
        reverse=True,
    ):
        if comparison.category not in adjusted or len(comparison.ranked_products) < 2:
            continue
        cheapest_index = _cheapest_option_index(comparison)
        current_index = adjusted[comparison.category]
        if cheapest_index is None or cheapest_index == current_index:
            continue
        current_cost = _option_cost(comparison.ranked_products[current_index])
        cheapest_cost = _option_cost(comparison.ranked_products[cheapest_index])
        if current_cost is None or cheapest_cost is None or cheapest_cost >= current_cost:
            continue
        adjusted[comparison.category] = cheapest_index
        notes.append("Swapped to a lower-cost {category} option to respect budget.".format(category=comparison.category))
        total = _selection_total(adjusted, comparisons)
        if total is not None and total <= budget:
            return adjusted, notes

    while len(adjusted) > 1:
        total = _selection_total(adjusted, comparisons)
        if total is None or total <= budget:
            break
        removable_category = max(
            adjusted,
            key=lambda category: (
                priority_by_category.get(category.lower(), 999),
                _selected_option_cost(category, adjusted, comparisons),
            ),
        )
        adjusted.pop(removable_category, None)
        notes.append("Dropped {category} from the first-pass stack to stay closer to budget.".format(category=removable_category))

    return adjusted, notes


def _cheapest_option_index(comparison: ProductComparison) -> Optional[int]:
    cheapest_index: Optional[int] = None
    cheapest_cost: Optional[float] = None
    for index, compared_product in enumerate(comparison.ranked_products):
        cost = _option_cost(compared_product)
        if cost is None:
            continue
        if cheapest_cost is None or cost < cheapest_cost:
            cheapest_cost = cost
            cheapest_index = index
    return cheapest_index


def _selection_total(selection: dict[str, int], comparisons: list[ProductComparison]) -> Optional[float]:
    total = 0.0
    has_cost = False
    for comparison in comparisons:
        selected_index = selection.get(comparison.category)
        if selected_index is None or selected_index >= len(comparison.ranked_products):
            continue
        cost = _option_cost(comparison.ranked_products[selected_index])
        if cost is None:
            continue
        total += cost
        has_cost = True
    return round(total, 2) if has_cost else None


def _selected_option_cost(category: str, selection: dict[str, int], comparisons: list[ProductComparison]) -> float:
    for comparison in comparisons:
        if comparison.category != category:
            continue
        selected_index = selection.get(category)
        if selected_index is None or selected_index >= len(comparison.ranked_products):
            return 0.0
        return _option_cost(comparison.ranked_products[selected_index]) or 0.0
    return 0.0


def _option_cost(compared_product) -> Optional[float]:
    if compared_product.monthly_cost is not None:
        return float(compared_product.monthly_cost)
    return estimate_monthly_cost(
        compared_product.product,
        servings_per_container=compared_product.ingredient_analysis.servings_per_container,
        price_per_serving=compared_product.ingredient_analysis.price_per_serving,
    )


def _default_dosage(category: str, compared_product) -> str:
    if compared_product.ingredient_analysis.dosage_summary:
        return compared_product.ingredient_analysis.dosage_summary
    normalized_category = category.lower()
    if normalized_category == "creatine":
        return "5 g daily"
    if normalized_category == "protein powder":
        return "1 serving as needed"
    if normalized_category == "magnesium":
        return "Take the label serving in the evening"
    return "Take the label serving daily"


def _default_cadence(category: str) -> str:
    normalized_category = category.lower()
    if normalized_category == "protein powder":
        return "Use post-workout or to close daily protein gaps"
    if normalized_category == "electrolytes":
        return "Use around training or hydration needs"
    if normalized_category == "magnesium":
        return "Daily, preferably in the evening"
    return "Daily"


def _fallback_summary(items: list[StackItem], total_monthly_cost: Optional[float], budget: float) -> str:
    if not items:
        return "No viable supplement stack could be assembled from the discovered products."
    if total_monthly_cost is None:
        return "Built a {count}-item supplement stack from the top-ranked category picks.".format(count=len(items))
    relation = "within" if total_monthly_cost <= budget else "above"
    return (
        "Built a {count}-item supplement stack with an estimated monthly cost of ${cost:.2f}, "
        "{relation} the ${budget:.2f} budget."
    ).format(
        count=len(items),
        cost=total_monthly_cost,
        relation=relation,
        budget=budget,
    )


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)
    return deduped
