from __future__ import annotations

from typing import Any, Dict, List

from shopper.schemas.common import NutritionPlan


class NutritionAccuracyEvaluator:
    def evaluate(self, case: Dict[str, Any], plan: NutritionPlan) -> Dict[str, Any]:
        expected = case["expected"]
        issues: List[str] = []

        tdee_delta = abs(plan.tdee - expected["tdee"]) / float(expected["tdee"])
        if tdee_delta > 0.05:
            issues.append("TDEE deviated by more than 5 percent.")

        macro_delta = {}
        for field_name in ("protein_g", "carbs_g", "fat_g"):
            expected_value = max(1, int(expected[field_name]))
            delta = abs(getattr(plan, field_name) - expected_value) / float(expected_value)
            macro_delta[field_name] = round(delta, 4)
            if delta > 0.10:
                issues.append("{field} deviated by more than 10 percent.".format(field=field_name))

        missing_restrictions = [
            restriction
            for restriction in list(case["profile"].get("dietary_restrictions", [])) + list(case["profile"].get("allergies", []))
            if restriction not in plan.applied_restrictions
        ]
        if missing_restrictions:
            issues.append("Dietary restrictions were not preserved in the plan metadata.")

        return {
            "case_id": case["case_id"],
            "passed": not issues,
            "tdee_delta_pct": round(tdee_delta, 4),
            "macro_delta_pct": macro_delta,
            "issues": issues,
        }
