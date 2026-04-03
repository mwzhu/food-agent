from __future__ import annotations

from typing import Any

from shopper.services.ingredient_aggregator import infer_category


class GroceryCategoryEvaluator:
    def evaluate(self, case: dict[str, Any]) -> dict[str, Any]:
        actual_category = infer_category(case["name"])
        issues: list[str] = []
        if actual_category != case["expected_category"]:
            issues.append(
                "Expected {name} to map to {expected} but got {actual}.".format(
                    name=case["name"],
                    expected=case["expected_category"],
                    actual=actual_category,
                )
            )
        return {
            "case_id": case["case_id"],
            "passed": not issues,
            "issues": issues,
            "actual_category": actual_category,
        }
