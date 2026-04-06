from __future__ import annotations

from shopper.schemas import PurchaseOrder
from shopper.services import check_budget


def test_check_budget_reports_within_budget_and_overage():
    orders = [
        PurchaseOrder(
            store="Walmart",
            items=[],
            subtotal=36.0,
            delivery_fee=4.0,
            total_cost=40.0,
            channel="online",
            status="pending",
        ),
        PurchaseOrder(
            store="Costco",
            items=[],
            subtotal=18.0,
            delivery_fee=0.0,
            total_cost=18.0,
            channel="in_store",
            status="pending",
        ),
    ]

    summary = check_budget(orders, budget=50.0)
    assert summary.total_cost == 58.0
    assert summary.within_budget is False
    assert summary.overage == 8.0
    assert summary.utilization == 1.16
