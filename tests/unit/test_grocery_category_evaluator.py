from __future__ import annotations

from shopper.evaluation.evaluators.grocery_category import GroceryCategoryEvaluator


def test_grocery_category_evaluator_uses_expected_category_dataset():
    evaluator = GroceryCategoryEvaluator()

    result = evaluator.evaluate(
        {
            "case_id": "spinach-produce",
            "name": "spinach",
            "expected_category": "produce",
        }
    )

    assert result["passed"] is True
    assert result["actual_category"] == "produce"
