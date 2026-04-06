from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from shopper.agents import invoke_planner_graph
from shopper.config import Settings
from shopper.evaluation.evaluators.daily_macro_alignment import DailyMacroAlignmentEvaluator
from shopper.evaluation.evaluators.groundedness import GroundednessEvaluator
from shopper.evaluation.evaluators.grocery_aggregation import GroceryAggregationEvaluator
from shopper.evaluation.evaluators.grocery_category import GroceryCategoryEvaluator
from shopper.evaluation.evaluators.grocery_completeness import GroceryCompletenessEvaluator
from shopper.evaluation.evaluators.grocery_fridge_diff import GroceryFridgeDiffEvaluator
from shopper.evaluation.evaluators.grocery_traceability import GroceryTraceabilityEvaluator
from shopper.evaluation.evaluators.meal_relevance import MealRelevanceEvaluator
from shopper.evaluation.evaluators.nutrition_accuracy import NutritionAccuracyEvaluator
from shopper.evaluation.evaluators.safety import SafetyEvaluator
from shopper.schemas import FridgeItemSnapshot, GroceryItem, MealSlot, NutritionPlan, PlannerStateSnapshot
from shopper.schemas.user import UserProfileBase
from shopper.services import (
    aggregate_quantities,
    calculate_macros,
    calculate_tdee,
    categorize,
    diff_against_fridge,
    extract_ingredients,
)


DATASET_DIR = Path(__file__).resolve().parent / "datasets"
class EvaluationRunner:
    def __init__(self, graph, settings: Settings, recipe_store) -> None:
        self.graph = graph
        self.settings = settings
        self.recipe_store = recipe_store
        self.nutrition_evaluator = NutritionAccuracyEvaluator()
        self.daily_macro_alignment_evaluator = DailyMacroAlignmentEvaluator()
        self.meal_relevance_evaluator = MealRelevanceEvaluator()
        self.safety_evaluator = SafetyEvaluator()
        self.groundedness_evaluator = GroundednessEvaluator()
        self.grocery_evaluator = GroceryCompletenessEvaluator()
        self.grocery_aggregation_evaluator = GroceryAggregationEvaluator()
        self.grocery_category_evaluator = GroceryCategoryEvaluator()
        self.grocery_fridge_diff_evaluator = GroceryFridgeDiffEvaluator()
        self.grocery_traceability_evaluator = GroceryTraceabilityEvaluator()

    async def run(self, eval_name: str) -> Dict[str, Any]:
        if eval_name == "nutrition":
            cases = self._load_cases("nutrition_cases.json")
            return self._run_nutrition_eval(cases)

        if eval_name == "grocery_category":
            cases = self._load_cases("grocery_category_cases.json")
            return self._run_grocery_category_eval(cases)

        if eval_name in {
            "grocery_completeness",
            "grocery_aggregation",
            "grocery_fridge_diff",
            "grocery_traceability",
        }:
            cases = self._load_cases("grocery_cases.json")
            return await self._run_grocery_eval(cases, eval_name)

        dataset_name = {
            "daily_macro_alignment": "meal_plan_cases.json",
            "meal_relevance": "meal_plan_cases.json",
            "safety": "safety_cases.json",
            "groundedness": "meal_plan_cases.json",
        }[eval_name]
        cases = self._load_cases(dataset_name)
        results = []
        for case in cases:
            initial_state = self._build_initial_state(case)
            graph_result = await invoke_planner_graph(self.graph, initial_state, self.settings, source="eval")
            evaluation = self._evaluate_case(eval_name, case, graph_result)
            results.append(
                {
                    "case_id": case["case_id"],
                    "passed": evaluation["passed"],
                    "issues": evaluation["issues"],
                    "trace_metadata": graph_result.get("trace_metadata", {}),
                    "nutrition_plan": graph_result.get("nutrition_plan"),
                    "selected_meals": graph_result.get("selected_meals", []),
                    "grocery_list": graph_result.get("grocery_list", []),
                    "profile": case["profile"],
                    **{key: value for key, value in evaluation.items() if key not in {"passed", "issues"}},
                }
            )

        passed = all(result["passed"] for result in results)
        upload = self._maybe_upload_results(eval_name, results)
        return {
            "eval_name": eval_name,
            "passed": passed,
            "num_cases": len(results),
            "pass_rate": round(sum(1 for result in results if result["passed"]) / float(len(results)), 4),
            "langsmith_upload": upload,
            "results": results,
        }

    def _run_grocery_category_eval(self, cases: list[dict[str, Any]]) -> dict[str, Any]:
        results = []
        for case in cases:
            evaluation = self.grocery_category_evaluator.evaluate(case)
            results.append(
                {
                    "case_id": case["case_id"],
                    "passed": evaluation["passed"],
                    "issues": evaluation["issues"],
                    "trace_metadata": {
                        "kind": "deterministic_component",
                        "project": self.settings.langsmith_project,
                        "trace_id": None,
                        "source": "eval",
                    },
                    "name": case["name"],
                    "expected_category": case["expected_category"],
                    **{key: value for key, value in evaluation.items() if key not in {"passed", "issues"}},
                }
            )

        passed = all(result["passed"] for result in results)
        upload = self._maybe_upload_results("grocery_category", results)
        return {
            "eval_name": "grocery_category",
            "passed": passed,
            "num_cases": len(results),
            "pass_rate": round(sum(1 for result in results if result["passed"]) / float(len(results)), 4),
            "langsmith_upload": upload,
            "results": results,
        }

    def _run_nutrition_eval(self, cases: list[dict[str, Any]]) -> dict[str, Any]:
        results = []
        for case in cases:
            plan = self._build_nutrition_plan(case["profile"])
            evaluation = self.nutrition_evaluator.evaluate(case, plan)
            results.append(
                {
                    "case_id": case["case_id"],
                    "passed": evaluation["passed"],
                    "issues": evaluation["issues"],
                    "trace_metadata": {
                        "kind": "deterministic_component",
                        "project": self.settings.langsmith_project,
                        "trace_id": None,
                        "source": "eval",
                    },
                    "nutrition_plan": plan.model_dump(mode="json"),
                    "selected_meals": [],
                    "grocery_list": [],
                    "profile": case["profile"],
                    **{key: value for key, value in evaluation.items() if key not in {"passed", "issues"}},
                }
            )

        passed = all(result["passed"] for result in results)
        upload = self._maybe_upload_results("nutrition", results)
        return {
            "eval_name": "nutrition",
            "passed": passed,
            "num_cases": len(results),
            "pass_rate": round(sum(1 for result in results if result["passed"]) / float(len(results)), 4),
            "langsmith_upload": upload,
            "results": results,
        }

    def _load_cases(self, dataset_name: str) -> list[dict[str, Any]]:
        cases = json.loads((DATASET_DIR / dataset_name).read_text(encoding="utf-8"))
        assert isinstance(cases, list)
        return cases

    async def _run_grocery_eval(self, cases: list[dict[str, Any]], eval_name: str) -> dict[str, Any]:
        results = []
        for case in cases:
            meals = self._build_case_meals(case)
            fridge_inventory = self._build_case_fridge_inventory(case)
            grocery_list = categorize(
                diff_against_fridge(
                    aggregate_quantities(extract_ingredients(meals)),
                    fridge_inventory,
                )
            )
            evaluation = self._evaluate_shopping_case(eval_name, case, meals, grocery_list, fridge_inventory)
            results.append(
                {
                    "case_id": case["case_id"],
                    "passed": evaluation["passed"],
                    "issues": evaluation["issues"],
                    "trace_metadata": {
                        "kind": "deterministic_component",
                        "project": self.settings.langsmith_project,
                        "trace_id": None,
                        "source": "eval",
                    },
                    "nutrition_plan": None,
                    "selected_meals": [meal.model_dump(mode="json") for meal in meals],
                    "grocery_list": [item.model_dump(mode="json") for item in grocery_list],
                    "meal_plan": case["meal_plan"],
                    "fridge_inventory": case["fridge_inventory"],
                    "critic_verdict": None,
                    **{key: value for key, value in evaluation.items() if key not in {"passed", "issues"}},
                }
            )

        passed = all(result["passed"] for result in results)
        upload = self._maybe_upload_results(eval_name, results)
        return {
            "eval_name": eval_name,
            "passed": passed,
            "num_cases": len(results),
            "pass_rate": round(sum(1 for result in results if result["passed"]) / float(len(results)), 4),
            "langsmith_upload": upload,
            "results": results,
        }

    def _build_initial_state(self, case: dict[str, Any]) -> dict[str, Any]:
        return PlannerStateSnapshot.starting(
            run_id="eval-{case_id}".format(case_id=case["case_id"]),
            user_id=case["case_id"],
            user_profile=case["profile"],
        ).model_dump(mode="json")

    def _build_case_meals(self, case: dict[str, Any]) -> list[MealSlot]:
        meals: list[MealSlot] = []
        for entry in case["meal_plan"]:
            recipe = self.recipe_store.get_recipe(entry["recipe_id"])
            assert recipe is not None, entry["recipe_id"]
            serving_multiplier = entry["serving_multiplier"]
            meals.append(
                MealSlot(
                    day=entry["day"],
                    meal_type=entry["meal_type"],
                    recipe_id=recipe.recipe_id,
                    recipe_name=recipe.name,
                    cuisine=recipe.cuisine,
                    prep_time_min=recipe.prep_time_min,
                    serving_multiplier=serving_multiplier,
                    calories=int(round(recipe.calories * serving_multiplier)),
                    protein_g=int(round(recipe.protein_g * serving_multiplier)),
                    carbs_g=int(round(recipe.carbs_g * serving_multiplier)),
                    fat_g=int(round(recipe.fat_g * serving_multiplier)),
                    tags=recipe.tags,
                    macro_fit_score=1.0,
                    recipe=recipe,
                )
            )
        return meals

    def _build_case_fridge_inventory(self, case: dict[str, Any]) -> list[FridgeItemSnapshot]:
        return [
            FridgeItemSnapshot(
                item_id=index,
                user_id=case["case_id"],
                name=item["name"],
                quantity=item["quantity"],
                unit=item["unit"],
                category=item["category"],
                expiry_date=item.get("expiry_date"),
            )
            for index, item in enumerate(case["fridge_inventory"], start=1)
        ]

    def _build_nutrition_plan(self, profile_payload: dict[str, Any]) -> NutritionPlan:
        profile = UserProfileBase.model_validate(profile_payload)
        tdee = calculate_tdee(profile)
        plan = calculate_macros(tdee=tdee, goal=profile.goal, sex=profile.sex)
        plan.applied_restrictions = sorted(set(profile.dietary_restrictions + profile.allergies))
        return plan

    def _evaluate_case(self, eval_name: str, case: dict[str, Any], graph_result: dict[str, Any]) -> dict[str, Any]:
        plan = NutritionPlan.model_validate(graph_result["nutrition_plan"])
        meals = [MealSlot.model_validate(item) for item in graph_result["selected_meals"]]
        grocery_list = [GroceryItem.model_validate(item) for item in graph_result["grocery_list"]]

        if eval_name == "nutrition":
            return self.nutrition_evaluator.evaluate(case, plan)
        if eval_name == "daily_macro_alignment":
            return self.daily_macro_alignment_evaluator.evaluate(case, plan, meals)
        if eval_name == "meal_relevance":
            return self.meal_relevance_evaluator.evaluate(case, meals, self.recipe_store.get_recipe)
        if eval_name == "safety":
            return self.safety_evaluator.evaluate(case, meals)
        if eval_name == "groundedness":
            return self.groundedness_evaluator.evaluate(case, meals, self.recipe_store.get_recipe)
        raise AssertionError(eval_name)

    def _evaluate_shopping_case(
        self,
        eval_name: str,
        case: dict[str, Any],
        meals: list[MealSlot],
        grocery_list: list[GroceryItem],
        fridge_inventory: list[FridgeItemSnapshot],
    ) -> dict[str, Any]:
        if eval_name == "grocery_completeness":
            return self.grocery_evaluator.evaluate(case, meals, grocery_list)
        if eval_name == "grocery_aggregation":
            return self.grocery_aggregation_evaluator.evaluate(case, meals, grocery_list)
        if eval_name == "grocery_fridge_diff":
            return self.grocery_fridge_diff_evaluator.evaluate(case, meals, grocery_list, fridge_inventory)
        if eval_name == "grocery_traceability":
            return self.grocery_traceability_evaluator.evaluate(case, meals, grocery_list)
        raise AssertionError(eval_name)

    def _maybe_upload_results(self, eval_name: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not self.settings.langsmith_tracing:
            return {"kind": "skipped", "reason": "Remote LangSmith upload is disabled."}

        assert self.settings.langsmith_api_key
        from langsmith import Client

        project_name = self.settings.langsmith_project
        client = Client(api_key=self.settings.langsmith_api_key)
        if not client.has_project(project_name):
            client.create_project(
                project_name=project_name,
                description="Phase 3 evaluation run for {name}".format(name=eval_name),
                metadata={"phase": "phase3", "eval_name": eval_name},
            )
        for result in results:
            run_id = uuid4()
            inputs = {"profile": result["profile"]} if "profile" in result else {
                "meal_plan": result.get("meal_plan", []),
                "fridge_inventory": result.get("fridge_inventory", []),
            }
            client.create_run(
                name="eval:{eval_name}:{case_id}".format(eval_name=eval_name, case_id=result["case_id"]),
                run_type="chain",
                inputs=inputs,
                project_name=project_name,
                id=run_id,
                start_time=datetime.now(timezone.utc),
                extra={"metadata": {"phase": "phase3", "eval_name": eval_name}},
            )
            client.update_run(
                run_id=run_id,
                end_time=datetime.now(timezone.utc),
                outputs={
                    "nutrition_plan": result["nutrition_plan"],
                    "grocery_list": result.get("grocery_list", []),
                },
                extra={"metadata": {"phase": "phase3", "eval_name": eval_name, "source": "eval"}},
            )
            client.create_feedback(
                run_id=run_id,
                key=eval_name,
                score=1 if result["passed"] else 0,
                comment="; ".join(result["issues"]) if result["issues"] else "passed",
            )
        return {"kind": "uploaded", "project_name": project_name}
