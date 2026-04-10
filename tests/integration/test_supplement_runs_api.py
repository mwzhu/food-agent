from __future__ import annotations

import asyncio
import time
from pathlib import Path

from fastapi.testclient import TestClient

from shopper.config import Settings
from shopper.main import create_app
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


def _make_client(tmp_path: Path) -> TestClient:
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

    return TestClient(
        create_app(
            _settings(tmp_path),
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
            "/v1/supplements/runs/{run_id}/approve".format(run_id=run_id),
            json={"approved_store_domains": []},
        )
        assert approve_response.status_code == 200, approve_response.text
        approved_run = approve_response.json()
        assert approved_run["status"] == "completed"
        assert approved_run["state_snapshot"]["approved_store_domains"]

        stream_response = client.get("/v1/supplements/runs/{run_id}/stream".format(run_id=run_id))
        assert stream_response.status_code == 200, stream_response.text
        assert "event: approval_requested" in stream_response.text
        assert "event: approval_resolved" in stream_response.text
        assert "event: run_completed" in stream_response.text

        final_run = client.get("/v1/supplements/runs/{run_id}".format(run_id=run_id)).json()
        assert final_run["status"] == "completed"
        assert final_run["state_snapshot"]["current_node"] == "approval_gate"

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
            "/v1/supplements/runs/{run_id}/approve".format(run_id=run_id),
            json={"approved_store_domains": ["unknown-store.com"]},
        )
        assert invalid_approval.status_code == 409, invalid_approval.text
        assert "Approved stores must be one of" in invalid_approval.json()["detail"]
