from __future__ import annotations

from dataclasses import dataclass
from math import isclose

from shopper.schemas import CartBuildResult, CartDiscrepancy, CartVerification, GroceryItem


def _normalize_name(value: str) -> str:
    return " ".join(value.lower().split())


@dataclass
class CartVerifier:
    subtotal_tolerance_ratio: float = 0.02

    def verify_cart(self, expected_items: list[GroceryItem], cart: CartBuildResult) -> CartVerification:
        discrepancies: list[CartDiscrepancy] = []
        expected_by_name = {_normalize_name(item.name): item for item in expected_items}
        actual_by_name = {_normalize_name(item.requested_name): item for item in cart.items}

        for normalized_name, expected in expected_by_name.items():
            actual = actual_by_name.get(normalized_name)
            if actual is None:
                discrepancies.append(
                    CartDiscrepancy(
                        code="missing_item",
                        message=f"Cart is missing '{expected.name}'.",
                        item_name=expected.name,
                        expected=str(expected.shopping_quantity or expected.quantity),
                        actual="missing",
                    )
                )
                continue

            expected_quantity = expected.shopping_quantity or expected.quantity
            if actual.actual_quantity != expected_quantity:
                discrepancies.append(
                    CartDiscrepancy(
                        code="wrong_quantity",
                        message=f"'{expected.name}' has the wrong quantity in cart.",
                        item_name=expected.name,
                        expected=str(expected_quantity),
                        actual=str(actual.actual_quantity),
                    )
                )

            if actual.status in {"missing", "removed"}:
                discrepancies.append(
                    CartDiscrepancy(
                        code="unavailable_item",
                        message=f"'{expected.name}' was not successfully added to cart.",
                        item_name=expected.name,
                        expected="added",
                        actual=actual.status,
                    )
                )

        for normalized_name, actual in actual_by_name.items():
            if normalized_name not in expected_by_name:
                discrepancies.append(
                    CartDiscrepancy(
                        code="unexpected_item",
                        message=f"Unexpected item '{actual.actual_name}' was added to cart.",
                        item_name=actual.actual_name,
                        expected="not present",
                        actual="present",
                    )
                )

        calculated_subtotal = round(sum(item.line_total for item in cart.items if item.status != "removed"), 2)
        if not isclose(calculated_subtotal, cart.subtotal, rel_tol=self.subtotal_tolerance_ratio, abs_tol=0.01):
            discrepancies.append(
                CartDiscrepancy(
                    code="subtotal_mismatch",
                    message="Cart subtotal does not match the sum of line items within tolerance.",
                    expected=f"{calculated_subtotal:.2f}",
                    actual=f"{cart.subtotal:.2f}",
                )
            )

        calculated_total = round(cart.subtotal + cart.delivery_fee - sum(c.amount for c in cart.coupons), 2)
        if not isclose(calculated_total, cart.total_cost, rel_tol=self.subtotal_tolerance_ratio, abs_tol=0.01):
            discrepancies.append(
                CartDiscrepancy(
                    code="total_mismatch",
                    message="Cart total does not match subtotal plus fees and coupons within tolerance.",
                    expected=f"{calculated_total:.2f}",
                    actual=f"{cart.total_cost:.2f}",
                )
            )

        return CartVerification(
            passed=not discrepancies,
            discrepancies=discrepancies,
            subtotal_expected=calculated_subtotal,
            subtotal_actual=cart.subtotal,
            delivery_fee_expected=cart.delivery_fee,
            delivery_fee_actual=cart.delivery_fee,
        )
