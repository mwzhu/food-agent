from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from shopper.agents import invoke_planner_graph
from shopper.config import Settings
from shopper.evaluation.evaluators.nutrition_accuracy import NutritionAccuracyEvaluator
from shopper.schemas import PlannerStateSnapshot, NutritionPlan


DATASET_PATH = Path(__file__).resolve().parent / "datasets" / "nutrition_cases.json"


class EvaluationRunner:
    def __init__(self, graph, settings: Settings) -> None:
        self.graph = graph
        self.settings = settings
        self.nutrition_evaluator = NutritionAccuracyEvaluator()

    async def run(self, eval_name: str) -> Dict[str, Any]:
        assert eval_name == "nutrition"
        cases = self._load_cases()
        results = []
        for case in cases:
            initial_state = PlannerStateSnapshot(
                run_id="eval-{case_id}".format(case_id=case["case_id"]),
                user_id=case["case_id"],
                user_profile=case["profile"],
                nutrition_plan=None,
                selected_meals=[],
                context_metadata=[],
                status="pending",
                current_node="created",
                trace_metadata={},
            ).model_dump(mode="json")

            graph_result = await invoke_planner_graph(self.graph, initial_state, self.settings, source="eval")
            assert "nutrition_plan" in graph_result
            plan = NutritionPlan.model_validate(graph_result["nutrition_plan"])
            evaluation = self.nutrition_evaluator.evaluate(case, plan)
            results.append(
                {
                    "case_id": case["case_id"],
                    "passed": evaluation["passed"],
                    "issues": evaluation["issues"],
                    "tdee_delta_pct": evaluation["tdee_delta_pct"],
                    "macro_delta_pct": evaluation["macro_delta_pct"],
                    "trace_metadata": graph_result.get("trace_metadata", {}),
                    "nutrition_plan": plan.model_dump(mode="json"),
                    "profile": case["profile"],
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

    def _load_cases(self) -> List[Dict[str, Any]]:
        cases = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        assert isinstance(cases, list)
        return cases

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
                description="Phase 1 evaluation run for {name}".format(name=eval_name),
                metadata={"phase": "phase1", "eval_name": eval_name},
            )
        for result in results:
            run_id = uuid4()
            client.create_run(
                name="eval:{eval_name}:{case_id}".format(eval_name=eval_name, case_id=result["case_id"]),
                run_type="chain",
                inputs={"profile": result["profile"]},
                project_name=project_name,
                id=run_id,
                start_time=datetime.now(timezone.utc),
                extra={"metadata": {"phase": "phase1", "eval_name": eval_name}},
            )
            client.update_run(
                run_id=run_id,
                end_time=datetime.now(timezone.utc),
                outputs={"nutrition_plan": result["nutrition_plan"]},
                extra={"metadata": {"phase": "phase1", "eval_name": eval_name, "source": "eval"}},
            )
            client.create_feedback(
                run_id=run_id,
                key="nutrition_accuracy",
                score=1 if result["passed"] else 0,
                comment="; ".join(result["issues"]) if result["issues"] else "passed",
            )
        return {"kind": "uploaded", "project_name": project_name}
