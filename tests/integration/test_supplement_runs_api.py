from __future__ import annotations

import asyncio
import inspect
import time
from pathlib import Path

from fastapi.testclient import TestClient

from shopper.agents.tools.browser_tools import BrowserCheckoutAgent
from shopper.config import Settings
from shopper.main import create_app
from shopper.schemas import OrderConfirmation
from shopper.supplements.models import SupplementRun
from shopper.supplements.schemas import StoreCart, StoreCartLine


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        SHOPPER_DATABASE_URL="sqlite+aiosqlite:///{path}".format(path=tmp_path / "supplement-api.db"),
        SHOPPER_APP_ENV="test",
        SHOPPER_QDRANT_URL=None,
        LANGSMITH_TRACING=False,
        SHOPPER_CHECKOUT_ARTIFACTS_DIR=str(tmp_path / "artifacts"),
    )


class FakeSupplementAgentCheckoutBackend:
    def __init__(self) -> None:
        self.task_overrides: list[str | None] = []

    async def build_cart(self, request, artifact_dir):
        raise AssertionError("build_cart should not be called for supplement agent checkout")

    async def apply_coupons(self, request, order, artifact_dir):
        return []

    async def complete_checkout(self, request, order, artifact_dir, *, task_override=None, status_callback=None):
        self.task_overrides.append(task_override)
        import asyncio as _asyncio

        if status_callback is not None:
            result = status_callback(
                {
                    "type": "browser_live_url",
                    "live_url": "https://live.browser-use.com/fake-supplement",
                    "cloud_browser_session_id": "cloud-session-123",
                }
            )
            if inspect.isawaitable(result):
                await result

        await _asyncio.sleep(0.01)
        return OrderConfirmation(
            confirmation_id="supp-confirm-123",
            total_cost=order.total_cost,
            confirmation_url=order.checkout_url,
            message="Browser agent placed the order.",
        )


def _make_client(tmp_path: Path, checkout_backend: FakeSupplementAgentCheckoutBackend | None = None) -> TestClient:
    async def fake_search_store(store_domain: str, query: str):
        price = 28.0 if "ritual" in store_domain else 32.0
        store_slug = store_domain.split(".")[0]
        return [
            {
                "store_domain": store_domain,
                "product_id": "sleep-magnesium-{store}".format(store=store_slug),
                "title": "Magnesium Glycinate Night Support",
                "description": "Chelated magnesium glycinate. 200 mg magnesium per serving. 30 servings.",
                "url": "https://{store}/products/sleep-magnesium".format(store=store_domain),
                "image_url": None,
                "image_alt_text": None,
                "product_type": "Supplement",
                "tags": ["sleep"],
                "price_range": {
                    "min_price": price,
                    "max_price": price,
                    "currency": "USD",
                },
                "variants": [
                    {
                        "variant_id": "sleep-magnesium-{store}-variant".format(store=store_slug),
                        "title": "Default Title",
                        "price": price,
                        "currency": "USD",
                        "available": True,
                        "image_url": None,
                    }
                ],
            }
        ]

    async def fake_update_cart(store_domain: str, variant_id: str, quantity: int, *, cart_id=None):
        resolved_cart_id = cart_id or "{store}-cart".format(store=store_domain.split(".")[0])
        total = 28.0 * quantity
        return StoreCart(
            store_domain=store_domain,
            cart_id=resolved_cart_id,
            checkout_url="https://{store}/cart/{cart_id}".format(store=store_domain, cart_id=resolved_cart_id),
            total_quantity=quantity,
            subtotal_amount=total,
            total_amount=total,
            currency="USD",
            lines=[
                StoreCartLine(
                    line_id="line-1",
                    product_id="product-{variant}".format(variant=variant_id),
                    product_title="Product {variant}".format(variant=variant_id),
                    variant_id=variant_id,
                    variant_title="Default Title",
                    quantity=quantity,
                    subtotal_amount=total,
                    total_amount=total,
                    currency="USD",
                )
            ],
            errors=[],
            instructions="Open the checkout URL to complete purchase.",
        )

    settings = _settings(tmp_path)
    checkout_agent = (
        BrowserCheckoutAgent(
            settings,
            automation_backend=checkout_backend,
            artifact_root=tmp_path / "artifacts",
        )
        if checkout_backend is not None
        else None
    )

    return TestClient(
        create_app(
            settings,
            checkout_agent=checkout_agent,
            supplement_search_store_fn=fake_search_store,
            supplement_update_cart_fn=fake_update_cart,
        )
    )


def _health_payload() -> dict:
    return {
        "age": 34,
        "weight_lbs": 175,
        "sex": "male",
        "health_goals": ["better sleep"],
        "current_supplements": [],
        "medications": [],
        "conditions": [],
        "allergies": [],
        "monthly_budget": 100,
    }


def _buyer_profile_payload() -> dict:
    return {
        "email": "supplement-user@example.com",
        "shipping_name": "Supplement User",
        "shipping_address": {
            "line1": "123 Main St",
            "city": "San Francisco",
            "state": "CA",
            "postal_code": "94105",
            "country_code": "US",
        },
        "billing_same_as_shipping": True,
        "billing_country": "US",
        "consent_granted": True,
        "autopurchase_enabled": False,
        "max_order_total": 150,
        "max_monthly_total": 300,
        "shop_pay_linked": False,
        "consent_version": "v1",
    }


def _wait_for_status(client: TestClient, run_id: str, terminal_statuses: set[str], timeout_seconds: float = 5.0) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = client.get("/v1/supplements/runs/{run_id}".format(run_id=run_id))
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] in terminal_statuses:
            return payload
        time.sleep(0.05)
    raise AssertionError("Supplement run {run_id} did not reach {statuses}.".format(run_id=run_id, statuses=terminal_statuses))


def test_supplement_run_api_create_and_approve_flow(tmp_path):
    client = _make_client(tmp_path)
    payload = {
        "user_id": "supp-demo",
        "health_profile": _health_payload(),
    }

    with client:
        response = client.post("/v1/supplements/runs", json=payload)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "running"
        assert body["state_snapshot"]["current_phase"] == "memory"

        run_id = body["run_id"]
        awaiting_approval = _wait_for_status(client, run_id, {"awaiting_approval"})
        assert awaiting_approval["state_snapshot"]["current_phase"] == "checkout"
        assert awaiting_approval["state_snapshot"]["recommended_stack"]["items"]
        assert awaiting_approval["state_snapshot"]["store_carts"]
        assert awaiting_approval["state_snapshot"]["trace_metadata"]["source"] == "api"

        approve_response = client.post(
            "/v1/supplements/runs/{run_id}/approve-stores".format(run_id=run_id),
            json={"approved_store_domains": []},
        )
        assert approve_response.status_code == 200, approve_response.text
        approved_run = approve_response.json()
        assert approved_run["status"] == "running"
        assert approved_run["state_snapshot"]["approved_store_domains"]
        assert approved_run["state_snapshot"]["buyer_profile_ready"] is False
        assert approved_run["state_snapshot"]["current_node"] == "buyer_profile_gate"

        buyer_profile_response = client.post(
            "/v1/supplements/runs/{run_id}/buyer-profile".format(run_id=run_id),
            json=_buyer_profile_payload(),
        )
        assert buyer_profile_response.status_code == 200, buyer_profile_response.text
        assert buyer_profile_response.json()["email"] == "supplement-user@example.com"

        checkout_start_response = client.post(
            "/v1/supplements/runs/{run_id}/checkout/start".format(run_id=run_id),
            json={},
        )
        assert checkout_start_response.status_code == 200, checkout_start_response.text
        checkout_run = checkout_start_response.json()
        assert checkout_run["status"] == "running"
        assert checkout_run["state_snapshot"]["checkout_sessions"]

        approved_store = checkout_run["state_snapshot"]["approved_store_domains"][0]
        checkout_session_response = client.get(
            "/v1/supplements/runs/{run_id}/checkout/{store}".format(run_id=run_id, store=approved_store)
        )
        assert checkout_session_response.status_code == 200, checkout_session_response.text
        checkout_session = checkout_session_response.json()
        assert checkout_session["store_domain"] == approved_store
        assert checkout_session["continue_url"]

        continue_response = client.post(
            "/v1/supplements/runs/{run_id}/checkout/{store}/continue".format(run_id=run_id, store=approved_store),
            json={"action": "mark_order_placed"},
        )
        assert continue_response.status_code == 200, continue_response.text
        final_run = continue_response.json()
        assert final_run["status"] == "completed"
        assert final_run["state_snapshot"]["order_confirmations"]

        stream_response = client.get("/v1/supplements/runs/{run_id}/stream".format(run_id=run_id))
        assert stream_response.status_code == 200, stream_response.text
        assert "event: approval_requested" in stream_response.text
        assert "event: approval_resolved" in stream_response.text
        assert "event: run_completed" in stream_response.text

        fetched_final_run = client.get("/v1/supplements/runs/{run_id}".format(run_id=run_id)).json()
        assert fetched_final_run["status"] == "completed"
        assert fetched_final_run["state_snapshot"]["current_node"] == "order_confirmation"

        async def assert_persisted() -> None:
            async with client.app.state.session_factory() as session:
                persisted_run = await session.get(SupplementRun, run_id)
                assert persisted_run is not None
                assert persisted_run.status == "completed"

        asyncio.run(assert_persisted())


def test_supplement_run_api_rejects_unknown_approved_store(tmp_path):
    client = _make_client(tmp_path)
    payload = {
        "user_id": "supp-demo",
        "health_profile": _health_payload(),
    }

    with client:
        response = client.post("/v1/supplements/runs", json=payload)
        assert response.status_code == 201, response.text
        run_id = response.json()["run_id"]

        _wait_for_status(client, run_id, {"awaiting_approval"})
        invalid_approval = client.post(
            "/v1/supplements/runs/{run_id}/approve-stores".format(run_id=run_id),
            json={"approved_store_domains": ["unknown-store.com"]},
        )
        assert invalid_approval.status_code == 409, invalid_approval.text
        assert "Approved stores must be one of" in invalid_approval.json()["detail"]


def test_supplement_run_api_agent_start_places_order(tmp_path):
    checkout_backend = FakeSupplementAgentCheckoutBackend()
    client = _make_client(tmp_path, checkout_backend=checkout_backend)
    payload = {
        "user_id": "supp-demo",
        "health_profile": _health_payload(),
    }

    with client:
        response = client.post("/v1/supplements/runs", json=payload)
        assert response.status_code == 201, response.text
        run_id = response.json()["run_id"]

        _wait_for_status(client, run_id, {"awaiting_approval"})

        approve_response = client.post(
            "/v1/supplements/runs/{run_id}/approve-stores".format(run_id=run_id),
            json={"approved_store_domains": []},
        )
        assert approve_response.status_code == 200, approve_response.text

        buyer_profile_response = client.post(
            "/v1/supplements/runs/{run_id}/buyer-profile".format(run_id=run_id),
            json=_buyer_profile_payload(),
        )
        assert buyer_profile_response.status_code == 200, buyer_profile_response.text

        agent_start_response = client.post(
            "/v1/supplements/runs/{run_id}/checkout/agent-start".format(run_id=run_id),
            json={
                "store_domains": [],
                "payment_credentials": {
                    "card_number": "4242424242424242",
                    "card_expiry": "12/30",
                    "card_cvv": "123",
                    "card_name": "Supplement User",
                },
            },
        )
        assert agent_start_response.status_code == 200, agent_start_response.text
        started_run = agent_start_response.json()
        assert started_run["status"] == "running"
        assert started_run["state_snapshot"]["checkout_sessions"]
        assert started_run["state_snapshot"]["checkout_sessions"][0]["presentation_mode"] == "agent"

        final_run = _wait_for_status(client, run_id, {"completed", "failed"})
        assert final_run["status"] == "completed"
        assert final_run["state_snapshot"]["checkout_sessions"][0]["status"] == "order_placed"
        assert (
            final_run["state_snapshot"]["checkout_sessions"][0]["embedded_state_payload"]["agent_live_url"]
            == "https://live.browser-use.com/fake-supplement"
        )
        assert final_run["state_snapshot"]["order_confirmations"]

        assert checkout_backend.task_overrides
        assert "Card number: 4242424242424242" in (checkout_backend.task_overrides[0] or "")

        async def assert_persisted() -> None:
            async with client.app.state.session_factory() as session:
                persisted_run = await session.get(SupplementRun, run_id)
                assert persisted_run is not None
                assert persisted_run.status == "completed"

        asyncio.run(assert_persisted())
