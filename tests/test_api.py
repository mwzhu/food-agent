from pathlib import Path

from fastapi.testclient import TestClient

from shopper.config import Settings
from shopper.main import create_app


def _make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        SHOPPER_DATABASE_URL=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        SHOPPER_APP_ENV="test",
        SHOPPER_APPROVAL_REQUIRED=True,
    )
    app = create_app(settings)
    return TestClient(app)


def test_run_lifecycle(tmp_path):
    client = _make_client(tmp_path)
    payload = {
        "user_id": "michael",
        "profile": {
            "age": 29,
            "sex": "male",
            "height_cm": 178,
            "weight_kg": 78,
            "activity_level": "moderate",
            "goal": "maintain",
            "dietary_restrictions": [],
            "allergies": [],
            "dislikes": ["cilantro"],
            "household_size": 1,
            "weekday_time_limit_minutes": 30,
            "preferred_stores": ["walmart"],
        },
        "budget_weekly": 120,
        "schedule_summary": "Weeknight meals only.",
        "pantry_snapshot": [{"name": "rice", "quantity": 4, "unit": "cup", "category": "pantry"}],
        "require_approval": True,
    }
    with client:
        create_response = client.post("/v1/runs", json=payload)
        assert create_response.status_code == 201, create_response.text
        body = create_response.json()
        assert body["status"] == "awaiting_approval"
        assert body["pending_interrupt"] is not None
        run_id = body["run_id"]

        bootstrap_response = client.post(
            "/v1/integrations/walmart/session/bootstrap",
            json={"user_id": "michael", "profile_id": "profile-123", "metadata": {"region": "us"}},
        )
        assert bootstrap_response.status_code == 202, bootstrap_response.text

        get_response = client.get(f"/v1/runs/{run_id}")
        assert get_response.status_code == 200, get_response.text
        assert get_response.json()["artifacts"]["meal_plan"]["recipes"]

        resume_response = client.post(
            f"/v1/runs/{run_id}/resume",
            json={"approved": True, "human_edit": {"notes": "Looks good", "remove_items": []}},
        )
        assert resume_response.status_code == 200, resume_response.text
        resumed = resume_response.json()
        assert resumed["status"] == "completed"
        assert resumed["artifacts"]["checkout_result"]["confirmation_id"]


def test_feedback_endpoint_persists_event(tmp_path):
    client = _make_client(tmp_path)
    with client:
        response = client.post(
            "/v1/feedback",
            json={
                "user_id": "michael",
                "run_id": None,
                "namespace": "meal_feedback",
                "content": "Loved the greek chicken bowls, too much cleanup on salmon.",
                "metadata": {"rating": 4},
            },
        )
        assert response.status_code == 202, response.text
