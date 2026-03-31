from __future__ import annotations

from shopper.schemas import BasketPlan, VerifierResult


def verify_basket_against_budget(basket_plan: BasketPlan, budget_weekly: float) -> VerifierResult:
    passed = basket_plan.estimated_total <= budget_weekly
    message = "Basket is within budget." if passed else "Basket exceeds budget."
    return VerifierResult(
        stage="shopping_critic",
        passed=passed,
        message=message,
        details={"estimated_total": basket_plan.estimated_total, "budget_weekly": budget_weekly},
    )


def verify_cart_snapshot(cart_snapshot: dict, basket_plan: BasketPlan) -> VerifierResult:
    planned_items = {item.item_name for item in basket_plan.items}
    cart_items = set(cart_snapshot.get("items", []))
    missing = sorted(planned_items - cart_items)
    unexpected = sorted(cart_items - planned_items)
    passed = not missing and not unexpected
    return VerifierResult(
        stage="execution_verifier",
        passed=passed,
        message="Cart matches basket plan." if passed else "Cart differs from basket plan.",
        details={"missing_items": missing, "unexpected_items": unexpected},
    )

