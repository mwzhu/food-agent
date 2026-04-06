from __future__ import annotations

from typing import Sequence

from shopper.schemas import BudgetSummary, PurchaseOrder


def check_budget(orders: Sequence[PurchaseOrder], budget: float) -> BudgetSummary:
    total_cost = round(sum(order.total_cost for order in orders), 2)
    overage = round(max(0.0, total_cost - budget), 2)
    within_budget = total_cost <= budget + 1e-9
    utilization = round(total_cost / budget, 4) if budget > 0 else 0.0
    return BudgetSummary(
        budget=budget,
        total_cost=total_cost,
        overage=overage,
        within_budget=within_budget,
        utilization=utilization,
    )
