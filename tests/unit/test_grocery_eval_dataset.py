from __future__ import annotations

import json
from pathlib import Path


def test_grocery_eval_dataset_has_fifteen_golden_cases() -> None:
    dataset_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "shopper"
        / "evaluation"
        / "datasets"
        / "grocery_cases.json"
    )
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))

    assert len(cases) == 15
    for case in cases:
        assert case["meal_plan"], case["case_id"]
        assert "expected" in case, case["case_id"]
        assert case["expected"]["items"], case["case_id"]
        assert case["expected"]["total_items"] == len(case["expected"]["items"]), case["case_id"]
