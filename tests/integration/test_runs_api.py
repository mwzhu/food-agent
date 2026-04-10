from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import time

from fastapi.testclient import TestClient

from shopper.agents.tools.browser_tools import BrowserCheckoutAgent
from shopper.agents.tools.browser_tools import CheckoutFlowError
from shopper.config import Settings
from shopper.main import create_app
from shopper.models import PlanRun
from shopper.schemas import (
    BrowserProfileSyncSession,
    BrowserProfileSyncStatus,
    CartBuildResult,
    CartLineItem,
    OrderConfirmation,
    PlannerStateSnapshot,
)


class FakeCheckoutBackend:
    def __init__(self) -> None:
        self.confirmation = OrderConfirmation(
            confirmation_id="confirm-123",
            total_cost=18.5,
            message="Order placed.",
        )

    async def build_cart(self, request, artifact_dir):
        items = []
        subtotal = 0.0
        for requested_item in request.items:
            quantity = requested_item.shopping_quantity or requested_item.quantity
            line_total = round(float(quantity) * 0.25, 2)
            subtotal += line_total
            items.append(
                CartLineItem(
                    requested_name=requested_item.name,
                    requested_quantity=quantity,
                    actual_name=requested_item.name,
                    actual_quantity=quantity,
                    unit=requested_item.unit,
                    unit_price=0.25,
                    line_total=line_total,
                    status="added",
                )
            )
        return CartBuildResult(
            store=request.store.store,
            store_url=request.store.start_url,
            items=items,
            subtotal=subtotal,
            delivery_fee=0,
            total_cost=subtotal,
            cart_url=f"{request.store.start_url}/cart",
        )

    async def apply_coupons(self, request, order, artifact_dir):
        return []

    async def complete_checkout(self, request, order, artifact_dir):
        return self.confirmation.model_copy(update={"total_cost": order.total_cost})


class FailingCheckoutBackend(FakeCheckoutBackend):
    async def complete_checkout(self, request, order, artifact_dir):
        raise CheckoutFlowError("No saved payment method was available to complete checkout.", code="missing_payment_method")


class FakeBrowserProfileManager:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.created_sessions = 0

    async def get_walmart_status(self) -> BrowserProfileSyncStatus:
        return BrowserProfileSyncStatus(
            store="Walmart",
            configured=True,
            ready=self.ready,
            profile_id="profile-123",
            profile_name="shopper-walmart-checkout",
            login_url="https://www.walmart.com/account/login",
            start_url="https://www.walmart.com/cp/grocery/976759",
            cookie_domains=["walmart.com"] if self.ready else [],
            last_used_at=datetime.now(timezone.utc),
            message="Ready." if self.ready else "Sync needed.",
        )

    async def create_walmart_sync_session(self) -> BrowserProfileSyncSession:
        self.created_sessions += 1
        return BrowserProfileSyncSession(
            store="Walmart",
            profile_id="profile-123",
            session_id=f"session-{self.created_sessions}",
            live_url="https://live.browser-use.com/fake",
            login_url="https://www.walmart.com/account/login",
            timeout_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            message="Open the live session and sign in.",
        )

    async def get_instacart_status(self) -> BrowserProfileSyncStatus:
        return BrowserProfileSyncStatus(
            store="Instacart",
            configured=True,
            ready=self.ready,
            profile_id="profile-123",
            profile_name="shopper-instacart-checkout",
            login_url="https://www.instacart.com/login",
            start_url="https://www.instacart.com/grocery-delivery",
            cookie_domains=["instacart.com"] if self.ready else [],
            last_used_at=datetime.now(timezone.utc),
            message="Ready." if self.ready else "Sync needed.",
        )

    async def create_instacart_sync_session(self) -> BrowserProfileSyncSession:
        self.created_sessions += 1
        return BrowserProfileSyncSession(
            store="Instacart",
            profile_id="profile-123",
            session_id=f"session-{self.created_sessions}",
            live_url="https://live.browser-use.com/fake",
            login_url="https://www.instacart.com/login",
            timeout_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            message="Open the live session and sign in.",
        )

    async def get_chatgpt_status(self) -> BrowserProfileSyncStatus:
        return BrowserProfileSyncStatus(
            store="ChatGPT",
            configured=True,
            ready=self.ready,
            profile_id="profile-123",
            profile_name="shopper-chatgpt-checkout",
            login_url="https://chatgpt.com/auth/login",
            start_url="https://chatgpt.com/",
            cookie_domains=["chatgpt.com"] if self.ready else [],
            last_used_at=datetime.now(timezone.utc),
            message="Ready." if self.ready else "Sync needed.",
        )

    async def create_chatgpt_sync_session(self) -> BrowserProfileSyncSession:
        self.created_sessions += 1
        return BrowserProfileSyncSession(
            store="ChatGPT",
            profile_id="profile-123",
            session_id=f"session-{self.created_sessions}",
            live_url="https://live.browser-use.com/fake",
            login_url="https://chatgpt.com/auth/login",
            timeout_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            message="Open the live session and sign in.",
        )


def _make_client(tmp_path: Path, checkout_backend: FakeCheckoutBackend | None = None) -> TestClient:
    settings = Settings(
        SHOPPER_DATABASE_URL="sqlite+aiosqlite:///{path}".format(path=tmp_path / "test.db"),
        SHOPPER_APP_ENV="test",
        SHOPPER_QDRANT_URL=None,
        LANGSMITH_TRACING=False,
        SHOPPER_CHECKOUT_ARTIFACTS_DIR=str(tmp_path / "artifacts"),
    )
    checkout_agent = (
        BrowserCheckoutAgent(
            settings,
            automation_backend=checkout_backend,
            artifact_root=tmp_path / "artifacts",
        )
        if checkout_backend is not None
        else None
    )
    app = create_app(settings, checkout_agent=checkout_agent)
    app.state.browser_profile_manager = FakeBrowserProfileManager(ready=True)
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


def _rewrite_run_for_manual_shopping(client: TestClient, run_id: str) -> None:
    async def rewrite() -> None:
        async with client.app.state.session_factory() as session:
            plan_run = await session.get(PlanRun, run_id)
            assert plan_run is not None
            snapshot = PlannerStateSnapshot.model_validate(plan_run.state_snapshot)
            snapshot = snapshot.model_copy(
                update={
                    "status": "failed",
                    "grocery_list": [],
                    "fridge_inventory": [],
                    "current_node": "critic",
                    "current_phase": "planning",
                    "phase_statuses": snapshot.phase_statuses.model_copy(
                        update={"planning": "failed", "shopping": "locked"}
                    ),
                }
            )
            plan_run.status = snapshot.status
            plan_run.state_snapshot = snapshot.model_dump(mode="json")
            await session.commit()

    import asyncio

    asyncio.run(rewrite())


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
        assert {"load_memory", "nutrition_planner", "meal_selector", "critic", "grocery_builder", "price_optimizer"} <= metadata_nodes
        assert completed_run["state_snapshot"]["critic_verdict"]["passed"] is True
        assert completed_run["state_snapshot"]["phase_statuses"]["planning"] == "completed"
        assert completed_run["state_snapshot"]["phase_statuses"]["shopping"] == "completed"
        assert completed_run["state_snapshot"]["grocery_list"]
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


def test_inventory_crud_flow(tmp_path):
    client = _make_client(tmp_path)
    user_payload = {
        "user_id": "inventory-user",
        "age": 30,
        "weight_lbs": 160,
        "height_in": 68,
        "sex": "female",
        "activity_level": "lightly_active",
        "goal": "maintain",
        "dietary_restrictions": [],
        "allergies": [],
                "budget_weekly": 500,
        "household_size": 1,
        "cooking_skill": "intermediate",
        "schedule_json": {"weeknight_dinner": "30m"},
    }

    with client:
        client.app.state.browser_profile_manager = FakeBrowserProfileManager(ready=True)
        create_user = client.post("/v1/users", json=user_payload)
        assert create_user.status_code == 201, create_user.text

        create_item = client.post(
            "/v1/users/inventory-user/inventory",
            json={
                "name": "spinach",
                "quantity": 2,
                "unit": "cup",
                "category": "produce",
                "expiry_date": "2026-04-04",
            },
        )
        assert create_item.status_code == 201, create_item.text
        item_id = create_item.json()["item_id"]

        list_items = client.get("/v1/users/inventory-user/inventory")
        assert list_items.status_code == 200, list_items.text
        assert len(list_items.json()) == 1

        update_item = client.put(
            f"/v1/users/inventory-user/inventory/{item_id}",
            json={"quantity": 3, "expiry_date": "2026-04-05"},
        )
        assert update_item.status_code == 200, update_item.text
        assert update_item.json()["quantity"] == 3

        delete_item = client.delete(f"/v1/users/inventory-user/inventory/{item_id}")
        assert delete_item.status_code == 204, delete_item.text
        assert client.get("/v1/users/inventory-user/inventory").json() == []


def test_full_run_builds_grocery_list_and_applies_full_and_partial_fridge_diff(tmp_path):
    client = _make_client(tmp_path)
    payload = {
        "user_id": "fridge-check",
        "profile": {
            "age": 29,
            "weight_lbs": 150,
            "height_in": 64,
            "sex": "female",
            "activity_level": "lightly_active",
            "goal": "maintain",
            "dietary_restrictions": [],
            "allergies": [],
                "budget_weekly": 500,
            "household_size": 1,
            "cooking_skill": "intermediate",
            "schedule_json": {"weeknight_dinner": "25m"},
        },
    }

    with client:
        first_run = client.post("/v1/runs", json=payload)
        assert first_run.status_code == 201, first_run.text
        completed_first = _wait_for_run_completion(client, first_run.json()["run_id"])
        first_grocery_list = completed_first["state_snapshot"]["grocery_list"]
        assert completed_first["state_snapshot"]["phase_statuses"]["planning"] == "completed"
        assert completed_first["state_snapshot"]["phase_statuses"]["shopping"] == "completed"
        assert first_grocery_list

        fully_owned_item = next(
            item
            for item in first_grocery_list
            if item["quantity"] > 0
        )
        partially_owned_item = next(
            item
            for item in first_grocery_list
            if item["name"] != fully_owned_item["name"] and item["quantity"] >= 0.5
        )

        inventory_response = client.post(
            "/v1/users/fridge-check/inventory",
            json={
                "name": fully_owned_item["name"],
                "quantity": fully_owned_item["quantity"],
                "unit": fully_owned_item["unit"],
                "category": fully_owned_item["category"],
                "expiry_date": "2026-04-05",
            },
        )
        assert inventory_response.status_code == 201, inventory_response.text
        partial_inventory_response = client.post(
            "/v1/users/fridge-check/inventory",
            json={
                "name": partially_owned_item["name"],
                "quantity": round(max(partially_owned_item["quantity"] / 2.0, 0.25), 2),
                "unit": partially_owned_item["unit"],
                "category": partially_owned_item["category"],
                "expiry_date": "2026-04-06",
            },
        )
        assert partial_inventory_response.status_code == 201, partial_inventory_response.text

        second_run = client.post("/v1/runs", json=payload)
        assert second_run.status_code == 201, second_run.text
        completed_second = _wait_for_run_completion(client, second_run.json()["run_id"])
        assert completed_second["state_snapshot"]["phase_statuses"]["planning"] == "completed"
        assert completed_second["state_snapshot"]["phase_statuses"]["shopping"] == "completed"
        assert len(completed_second["state_snapshot"]["selected_meals"]) == 28
        assert completed_second["state_snapshot"]["grocery_list"]

        owned_item = next(
            item
            for item in completed_second["state_snapshot"]["grocery_list"]
            if item["name"] == fully_owned_item["name"]
        )
        partial_item = next(
            item
            for item in completed_second["state_snapshot"]["grocery_list"]
            if item["name"] == partially_owned_item["name"]
        )
        assert owned_item["already_have"] is True
        assert owned_item["shopping_quantity"] == 0
        assert partial_item["already_have"] is False
        assert 0 < partial_item["quantity_in_fridge"] < partial_item["quantity"]
        assert 0 < partial_item["shopping_quantity"] < partial_item["quantity"]


def test_post_shopping_run_starts_from_existing_meal_plan(tmp_path):
    client = _make_client(tmp_path)
    payload = {
        "user_id": "manual-shopping",
        "profile": {
            "age": 33,
            "weight_lbs": 168,
            "height_in": 69,
            "sex": "male",
            "activity_level": "lightly_active",
            "goal": "maintain",
            "dietary_restrictions": [],
            "allergies": [],
            "budget_weekly": 135,
            "household_size": 2,
            "cooking_skill": "intermediate",
            "schedule_json": {"weeknight_dinner": "30m"},
        },
    }

    with client:
        source_response = client.post("/v1/runs", json=payload)
        assert source_response.status_code == 201, source_response.text
        source_run = _wait_for_run_completion(client, source_response.json()["run_id"])
        assert source_run["state_snapshot"]["selected_meals"]

        _rewrite_run_for_manual_shopping(client, source_run["run_id"])

        shopping_response = client.post(f"/v1/runs/{source_run['run_id']}/shopping")
        assert shopping_response.status_code == 201, shopping_response.text
        shopping_run = shopping_response.json()
        assert shopping_run["run_id"] != source_run["run_id"]
        assert shopping_run["status"] == "running"
        assert shopping_run["state_snapshot"]["current_phase"] == "shopping"
        assert shopping_run["state_snapshot"]["phase_statuses"]["planning"] == "completed"
        assert shopping_run["state_snapshot"]["phase_statuses"]["shopping"] == "running"
        assert len(shopping_run["state_snapshot"]["selected_meals"]) == len(source_run["state_snapshot"]["selected_meals"])

        completed_shopping_run = _wait_for_run_completion(client, shopping_run["run_id"])
        assert completed_shopping_run["status"] == "completed"
        assert completed_shopping_run["state_snapshot"]["phase_statuses"]["planning"] == "completed"
        assert completed_shopping_run["state_snapshot"]["phase_statuses"]["shopping"] == "completed"
        assert completed_shopping_run["state_snapshot"]["grocery_list"]


def test_resume_endpoint_returns_not_found_for_unknown_runs(tmp_path):
    client = _make_client(tmp_path)
    with client:
        response = client.post(
            "/v1/runs/example-run/resume",
            json={"decision": "approve", "edits": []},
        )
        assert response.status_code == 404, response.text
        assert response.json()["detail"] == "Run not found."


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
            "budget_weekly": 500,
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


def test_walmart_profile_sync_routes_return_status_and_live_session(tmp_path):
    client = _make_client(tmp_path)

    with client:
        client.app.state.browser_profile_manager = FakeBrowserProfileManager(ready=False)

        status_response = client.get("/v1/checkout/walmart/profile-sync")
        assert status_response.status_code == 200, status_response.text
        assert status_response.json()["configured"] is True
        assert status_response.json()["ready"] is False

        session_response = client.post("/v1/checkout/walmart/profile-sync/session")
        assert session_response.status_code == 201, session_response.text
        assert session_response.json()["live_url"] == "https://live.browser-use.com/fake"


def test_instacart_profile_sync_routes_return_status_and_live_session(tmp_path):
    client = _make_client(tmp_path)

    with client:
        client.app.state.browser_profile_manager = FakeBrowserProfileManager(ready=False)

        status_response = client.get("/v1/checkout/instacart/profile-sync")
        assert status_response.status_code == 200, status_response.text
        assert status_response.json()["store"] == "Instacart"
        assert status_response.json()["configured"] is True
        assert status_response.json()["ready"] is False

        session_response = client.post("/v1/checkout/instacart/profile-sync/session")
        assert session_response.status_code == 201, session_response.text
        assert session_response.json()["store"] == "Instacart"
        assert session_response.json()["live_url"] == "https://live.browser-use.com/fake"


def test_walmart_smoke_run_creates_two_item_checkout_flow(tmp_path):
    client = _make_client(tmp_path, checkout_backend=FakeCheckoutBackend())
    user_payload = {
        "user_id": "smoke-checkout",
        "age": 29,
        "weight_lbs": 165,
        "height_in": 70,
        "sex": "male",
        "activity_level": "moderately_active",
        "goal": "maintain",
        "dietary_restrictions": [],
        "allergies": [],
        "budget_weekly": 500,
        "household_size": 1,
        "cooking_skill": "intermediate",
        "schedule_json": {"weeknight_dinner": "30m"},
    }

    with client:
        client.app.state.browser_profile_manager = FakeBrowserProfileManager(ready=True)
        create_user = client.post("/v1/users", json=user_payload)
        assert create_user.status_code == 201, create_user.text

        smoke_run = client.post("/v1/checkout/walmart/smoke-run", json={"user_id": "smoke-checkout"})
        assert smoke_run.status_code == 201, smoke_run.text
        assert smoke_run.json()["state_snapshot"]["current_phase"] == "checkout"

        awaiting_review = _wait_for_run_completion(client, smoke_run.json()["run_id"])
        assert awaiting_review["status"] == "awaiting_approval"
        grocery_list = awaiting_review["state_snapshot"]["grocery_list"]
        assert [item["name"] for item in grocery_list] == ["bananas", "protein bar"]
        assert [item["shopping_quantity"] for item in grocery_list] == [6, 1]
        requested_items = awaiting_review["state_snapshot"]["purchase_orders"][0]["requested_items"]
        assert [item["name"] for item in requested_items] == ["bananas", "protein bar"]


def test_instacart_smoke_run_creates_two_item_checkout_flow(tmp_path):
    client = _make_client(tmp_path, checkout_backend=FakeCheckoutBackend())
    user_payload = {
        "user_id": "instacart-smoke",
        "age": 29,
        "weight_lbs": 165,
        "height_in": 70,
        "sex": "male",
        "activity_level": "moderately_active",
        "goal": "maintain",
        "dietary_restrictions": [],
        "allergies": [],
        "budget_weekly": 500,
        "household_size": 1,
        "cooking_skill": "intermediate",
        "schedule_json": {"weeknight_dinner": "30m"},
    }

    with client:
        client.app.state.browser_profile_manager = FakeBrowserProfileManager(ready=True)
        create_user = client.post("/v1/users", json=user_payload)
        assert create_user.status_code == 201, create_user.text

        smoke_run = client.post("/v1/checkout/instacart/smoke-run", json={"user_id": "instacart-smoke"})
        assert smoke_run.status_code == 201, smoke_run.text
        assert smoke_run.json()["state_snapshot"]["current_phase"] == "checkout"

        awaiting_review = _wait_for_run_completion(client, smoke_run.json()["run_id"])
        assert awaiting_review["status"] == "awaiting_approval"
        grocery_list = awaiting_review["state_snapshot"]["grocery_list"]
        assert [item["name"] for item in grocery_list] == ["bananas", "protein bar"]
        assert [item["shopping_quantity"] for item in grocery_list] == [6, 1]
        requested_items = awaiting_review["state_snapshot"]["purchase_orders"][0]["requested_items"]
        assert [item["name"] for item in requested_items] == ["bananas", "protein bar"]
        assert awaiting_review["state_snapshot"]["purchase_orders"][0]["store"] == "Instacart"


def test_chatgpt_profile_sync_endpoints_work(tmp_path):
    client = _make_client(tmp_path)
    with client:
        client.app.state.browser_profile_manager = FakeBrowserProfileManager()
        status_response = client.get("/v1/checkout/chatgpt/profile-sync")
        assert status_response.status_code == 200, status_response.text
        assert status_response.json()["store"] == "ChatGPT"

        session_response = client.post("/v1/checkout/chatgpt/profile-sync/session")
        assert session_response.status_code == 201, session_response.text
        assert session_response.json()["store"] == "ChatGPT"


def test_chatgpt_instacart_smoke_run_creates_two_item_checkout_flow(tmp_path):
    client = _make_client(tmp_path, checkout_backend=FakeCheckoutBackend())
    payload = {
        "user_id": "chatgpt-smoke",
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
        client.app.state.browser_profile_manager = FakeBrowserProfileManager(ready=True)
        create_user = client.post("/v1/runs", json=payload)
        assert create_user.status_code == 201, create_user.text
        _wait_for_run_completion(client, create_user.json()["run_id"])

        smoke_run = client.post("/v1/checkout/chatgpt/instacart/smoke-run", json={"user_id": "chatgpt-smoke"})
        assert smoke_run.status_code == 201, smoke_run.text
        assert smoke_run.json()["state_snapshot"]["current_phase"] == "checkout"
        assert smoke_run.json()["state_snapshot"]["purchase_orders"][0]["store"] == "ChatGPT Instacart"

        awaiting_review = _wait_for_run_completion(client, smoke_run.json()["run_id"])
        assert awaiting_review["status"] == "awaiting_approval"
        assert awaiting_review["state_snapshot"]["purchase_orders"][0]["store"] == "ChatGPT Instacart"


def test_chatgpt_instacart_smoke_run_requires_ready_profile(tmp_path):
    client = _make_client(tmp_path, checkout_backend=FakeCheckoutBackend())
    user_payload = {
        "user_id": "chatgpt-not-ready",
        "age": 29,
        "weight_lbs": 165,
        "height_in": 70,
        "sex": "male",
        "activity_level": "moderately_active",
        "goal": "maintain",
        "dietary_restrictions": [],
        "allergies": [],
        "budget_weekly": 500,
        "household_size": 1,
        "cooking_skill": "intermediate",
        "schedule_json": {"weeknight_dinner": "30m"},
    }

    with client:
        client.app.state.browser_profile_manager = FakeBrowserProfileManager(ready=False)
        create_user = client.post("/v1/users", json=user_payload)
        assert create_user.status_code == 201, create_user.text

        smoke_run = client.post("/v1/checkout/chatgpt/instacart/smoke-run", json={"user_id": "chatgpt-not-ready"})
        assert smoke_run.status_code == 409, smoke_run.text
        assert "not ready yet" in smoke_run.json()["detail"].lower()


def test_checkout_run_waits_for_approval_and_can_resume(tmp_path):
    client = _make_client(tmp_path, checkout_backend=FakeCheckoutBackend())
    payload = {
        "user_id": "checkout-flow",
        "profile": {
            "age": 29,
            "weight_lbs": 165,
            "height_in": 70,
            "sex": "male",
            "activity_level": "moderately_active",
            "goal": "maintain",
            "dietary_restrictions": [],
            "allergies": [],
            "budget_weekly": 500,
            "household_size": 1,
            "cooking_skill": "intermediate",
            "schedule_json": {"weeknight_dinner": "30m"},
        },
    }

    with client:
        source_run = client.post("/v1/runs", json=payload)
        assert source_run.status_code == 201, source_run.text
        completed_source = _wait_for_run_completion(client, source_run.json()["run_id"])
        assert completed_source["status"] == "completed"

        checkout_run = client.post(
            f"/v1/runs/{completed_source['run_id']}/checkout",
            json={
                "store": "Demo Store",
                "start_url": "https://demo.example",
                "allowed_domains": ["demo.example"],
            },
        )
        assert checkout_run.status_code == 201, checkout_run.text

        awaiting_review = _wait_for_run_completion(client, checkout_run.json()["run_id"])
        assert awaiting_review["status"] == "awaiting_approval"
        assert awaiting_review["state_snapshot"]["current_phase"] == "checkout"
        assert awaiting_review["state_snapshot"]["purchase_orders"][0]["status"] == "awaiting_approval"
        assert awaiting_review["state_snapshot"]["purchase_orders"][0]["allowed_domains"] == ["demo.example"]

        resumed = client.post(
            f"/v1/runs/{awaiting_review['run_id']}/resume",
            json={"decision": "approve", "reason": "Looks good", "edits": []},
        )
        assert resumed.status_code == 200, resumed.text
        finished_checkout = _wait_for_run_completion(client, awaiting_review["run_id"])
        assert finished_checkout["status"] == "completed"
        assert finished_checkout["state_snapshot"]["purchase_orders"][0]["status"] == "purchased"
        assert finished_checkout["state_snapshot"]["purchase_orders"][0]["confirmation"]["confirmation_id"] == "confirm-123"


def test_checkout_rejection_marks_run_failed(tmp_path):
    client = _make_client(tmp_path, checkout_backend=FakeCheckoutBackend())
    payload = {
        "user_id": "checkout-reject",
        "profile": {
            "age": 29,
            "weight_lbs": 165,
            "height_in": 70,
            "sex": "male",
            "activity_level": "moderately_active",
            "goal": "maintain",
            "dietary_restrictions": [],
            "allergies": [],
            "budget_weekly": 500,
            "household_size": 1,
            "cooking_skill": "intermediate",
            "schedule_json": {"weeknight_dinner": "30m"},
        },
    }

    with client:
        source_run = client.post("/v1/runs", json=payload)
        assert source_run.status_code == 201, source_run.text
        completed_source = _wait_for_run_completion(client, source_run.json()["run_id"])

        checkout_run = client.post(
            f"/v1/runs/{completed_source['run_id']}/checkout",
            json={
                "store": "Demo Store",
                "start_url": "https://demo.example",
            },
        )
        assert checkout_run.status_code == 201, checkout_run.text
        awaiting_review = _wait_for_run_completion(client, checkout_run.json()["run_id"])
        assert awaiting_review["status"] == "awaiting_approval"

        rejected = client.post(
            f"/v1/runs/{awaiting_review['run_id']}/resume",
            json={"decision": "reject", "reason": "Need to edit the cart", "edits": []},
        )
        assert rejected.status_code == 200, rejected.text
        rejected_payload = rejected.json()
        assert rejected_payload["status"] == "failed"
        assert rejected_payload["state_snapshot"]["purchase_orders"][0]["status"] == "failed"


def test_checkout_failure_surfaces_reason_when_payment_method_is_missing(tmp_path):
    client = _make_client(tmp_path, checkout_backend=FailingCheckoutBackend())
    payload = {
        "user_id": "checkout-failure",
        "profile": {
            "age": 29,
            "weight_lbs": 165,
            "height_in": 70,
            "sex": "male",
            "activity_level": "moderately_active",
            "goal": "maintain",
            "dietary_restrictions": [],
            "allergies": [],
            "budget_weekly": 500,
            "household_size": 1,
            "cooking_skill": "intermediate",
            "schedule_json": {"weeknight_dinner": "30m"},
        },
    }

    with client:
        source_run = client.post("/v1/runs", json=payload)
        assert source_run.status_code == 201, source_run.text
        completed_source = _wait_for_run_completion(client, source_run.json()["run_id"])

        checkout_run = client.post(
            f"/v1/runs/{completed_source['run_id']}/checkout",
            json={
                "store": "Demo Store",
                "start_url": "https://demo.example",
            },
        )
        assert checkout_run.status_code == 201, checkout_run.text
        awaiting_review = _wait_for_run_completion(client, checkout_run.json()["run_id"])
        assert awaiting_review["status"] == "awaiting_approval"

        resumed = client.post(
            f"/v1/runs/{awaiting_review['run_id']}/resume",
            json={"decision": "approve", "reason": "Ship it", "edits": []},
        )
        assert resumed.status_code == 200, resumed.text
        failed_checkout = _wait_for_run_completion(client, awaiting_review["run_id"])
        assert failed_checkout["status"] == "failed"
        order = failed_checkout["state_snapshot"]["purchase_orders"][0]
        assert order["status"] == "failed"
        assert order["failure_code"] == "missing_payment_method"
        assert "payment method" in order["failure_reason"].lower()
