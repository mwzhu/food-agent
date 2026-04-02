from __future__ import annotations

from pathlib import Path
import time

from fastapi.testclient import TestClient

from shopper.config import Settings
from shopper.main import create_app


def _make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        SHOPPER_DATABASE_URL="sqlite+aiosqlite:///{path}".format(path=tmp_path / "test.db"),
        SHOPPER_APP_ENV="test",
        LANGSMITH_TRACING=False,
    )
    app = create_app(settings)
    return TestClient(app)


def _wait_for_run_completion(client: TestClient, run_id: str, timeout_seconds: float = 5.0) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = client.get(f"/v1/runs/{run_id}")
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] != "running":
            return payload
        time.sleep(0.05)
    raise AssertionError(f"Run {run_id} did not complete within {timeout_seconds} seconds.")


def test_post_run_completes_and_persists_state(tmp_path):
    client = _make_client(tmp_path)
    payload = {
        "user_id": "michael",
        "profile": {
            "age": 29,
            "weight_lbs": 176,
            "height_in": 70,
            "sex": "male",
            "activity_level": "moderately_active",
            "goal": "maintain",
            "dietary_restrictions": [],
            "allergies": [],
            "budget_weekly": 140,
            "household_size": 2,
            "cooking_skill": "intermediate",
            "schedule_json": {"weekday_dinners": "30m", "weekend": "flexible"},
        },
    }

    with client:
        response = client.post("/v1/runs", json=payload)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "running"
        assert body["state_snapshot"]["current_phase"] == "memory"

        run_id = body["run_id"]
        completed_run = _wait_for_run_completion(client, run_id)
        assert completed_run["run_id"] == run_id
        assert completed_run["status"] == "completed"
        assert completed_run["state_snapshot"]["nutrition_plan"]["tdee"] > 0
        assert len(completed_run["state_snapshot"]["selected_meals"]) == 28
        assert {"breakfast", "lunch", "dinner", "snack"} == {
            meal["meal_type"] for meal in completed_run["state_snapshot"]["selected_meals"]
        }
        metadata_nodes = {
            entry["node_name"]
            for entry in completed_run["state_snapshot"]["context_metadata"]
        }
        assert {"load_memory", "nutrition_planner", "meal_selector", "critic"} <= metadata_nodes
        assert completed_run["state_snapshot"]["critic_verdict"]["passed"] is True
        assert completed_run["state_snapshot"]["phase_statuses"]["planning"] == "completed"
        assert completed_run["state_snapshot"]["trace_metadata"]["trace_id"]
        assert completed_run["state_snapshot"]["trace_metadata"]["source"] == "api"


def test_user_crud_flow(tmp_path):
    client = _make_client(tmp_path)
    payload = {
        "user_id": "casey",
        "age": 34,
        "weight_lbs": 145,
        "height_in": 65,
        "sex": "female",
        "activity_level": "lightly_active",
        "goal": "cut",
        "dietary_restrictions": ["vegetarian"],
        "allergies": ["peanut"],
        "budget_weekly": 110,
        "household_size": 1,
        "cooking_skill": "beginner",
        "schedule_json": {"weekdays": "quick"},
    }

    with client:
        create_response = client.post("/v1/users", json=payload)
        assert create_response.status_code == 201, create_response.text
        update_response = client.put("/v1/users/casey", json={"budget_weekly": 125})
        assert update_response.status_code == 200, update_response.text
        get_response = client.get("/v1/users/casey")
        assert get_response.status_code == 200, get_response.text
        assert get_response.json()["budget_weekly"] == 125


def test_resume_endpoint_is_explicitly_deferred_in_phase_one(tmp_path):
    client = _make_client(tmp_path)
    with client:
        response = client.post("/v1/runs/example-run/resume")
        assert response.status_code == 501, response.text
        assert response.json()["detail"] == "Resume is not available in Phase 1."


def test_list_runs_and_trace_endpoint(tmp_path):
    client = _make_client(tmp_path)
    payload = {
        "user_id": "sam",
        "profile": {
            "age": 31,
            "weight_lbs": 182,
            "height_in": 71,
            "sex": "male",
            "activity_level": "lightly_active",
            "goal": "bulk",
            "dietary_restrictions": [],
            "allergies": [],
            "budget_weekly": 160,
            "household_size": 2,
            "cooking_skill": "advanced",
            "schedule_json": {"weeknights": "45m"},
        },
    }

    with client:
        first = client.post("/v1/runs", json=payload)
        assert first.status_code == 201, first.text
        second = client.post("/v1/runs", json=payload)
        assert second.status_code == 201, second.text
        _wait_for_run_completion(client, first.json()["run_id"])
        _wait_for_run_completion(client, second.json()["run_id"])

        list_response = client.get("/v1/runs", params={"user_id": "sam", "limit": 1})
        assert list_response.status_code == 200, list_response.text
        listed_runs = list_response.json()
        assert len(listed_runs) == 1
        assert listed_runs[0]["user_id"] == "sam"

        trace_response = client.get(f"/v1/runs/{listed_runs[0]['run_id']}/trace")
        assert trace_response.status_code == 200, trace_response.text
        trace_body = trace_response.json()
        assert trace_body["run_id"] == listed_runs[0]["run_id"]
        assert trace_body["trace_id"]
        assert trace_body["source"] == "api"


def test_run_stream_endpoint_replays_events(tmp_path):
    client = _make_client(tmp_path)
    payload = {
        "user_id": "streamer",
        "profile": {
            "age": 29,
            "weight_lbs": 150,
            "height_in": 64,
            "sex": "female",
            "activity_level": "lightly_active",
            "goal": "maintain",
            "dietary_restrictions": ["vegetarian"],
            "allergies": [],
            "budget_weekly": 120,
            "household_size": 1,
            "cooking_skill": "intermediate",
            "schedule_json": {"weeknight_dinner": "25m"},
        },
    }

    with client:
        run_response = client.post("/v1/runs", json=payload)
        assert run_response.status_code == 201, run_response.text
        run_id = run_response.json()["run_id"]

        events = []
        with client.stream("GET", f"/v1/runs/{run_id}/stream") as response:
            assert response.status_code == 200, response.text
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                events.append(line.removeprefix("data: "))
                if len(events) >= 3:
                    break

        assert events, "Expected stream endpoint to emit at least one event."
