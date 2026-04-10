from __future__ import annotations

import asyncio
from typing import Any

from shopper.config import Settings
from shopper.supplements.agents.graph import build_supplement_graph, invoke_supplement_graph
from shopper.supplements.agents.supervisor import route_from_critic, route_from_supervisor
from shopper.supplements.schemas import (
    HealthProfile,
    ShopifyPriceRange,
    ShopifyProduct,
    ShopifyProductVariant,
    SupplementCriticVerdict,
    SupplementStateSnapshot,
)
from shopper.supplements.schemas.recommendation import StoreCart, StoreCartLine


def _settings() -> Settings:
    return Settings(SHOPPER_APP_ENV="test", LANGSMITH_TRACING=False)


def _health_profile(**overrides: Any) -> HealthProfile:
    payload = {
        "age": 34,
        "weight_lbs": 175,
        "sex": "male",
        "health_goals": ["better sleep"],
        "current_supplements": [],
        "medications": [],
        "conditions": [],
        "allergies": [],
        "monthly_budget": 80,
    }
    payload.update(overrides)
    return HealthProfile.model_validate(payload)


def _product(
    *,
    store_domain: str,
    product_id: str,
    title: str,
    price: float,
    description: str,
) -> ShopifyProduct:
    return ShopifyProduct(
        store_domain=store_domain,
        product_id=product_id,
        title=title,
        description=description,
        url="https://{store_domain}/products/{product_id}".format(
            store_domain=store_domain,
            product_id=product_id,
        ),
        image_url=None,
        image_alt_text=None,
        product_type="Supplement",
        tags=["sleep"],
        price_range=ShopifyPriceRange(min_price=price, max_price=price, currency="USD"),
        variants=[
            ShopifyProductVariant(
                variant_id="{product_id}-variant".format(product_id=product_id),
                title="Default Title",
                price=price,
                currency="USD",
                available=True,
                image_url=None,
            )
        ],
    )


def test_supplement_supervisor_routes_completed_runs_to_end():
    assert route_from_supervisor({"status": "awaiting_approval", "current_phase": "checkout"}) == "end"
    assert route_from_supervisor({"status": "completed", "current_phase": "analysis"}) == "end"


def test_supplement_supervisor_routes_partial_analysis_to_critic():
    assert route_from_supervisor({"current_phase": "analysis", "recommended_stack": {"items": [{}]}}) == "critic_subgraph"
    assert route_from_supervisor({"current_phase": "analysis"}) == "analysis_subgraph"
    assert (
        route_from_supervisor(
            {
                "current_phase": "analysis",
                "recommended_stack": {"items": [{}]},
                "critic_verdict": {"decision": "failed"},
            }
        )
        == "analysis_subgraph"
    )


def test_supplement_critic_routing_respects_replan_limit():
    assert (
        route_from_critic(
            {"critic_verdict": {"decision": "passed"}, "replan_count": 0},
            max_replans=1,
        )
        == "checkout_subgraph"
    )
    assert (
        route_from_critic(
            {"critic_verdict": {"decision": "failed"}, "replan_count": 0},
            max_replans=1,
        )
        == "analysis_subgraph"
    )
    assert (
        route_from_critic(
            {"critic_verdict": {"decision": "failed"}, "replan_count": 1},
            max_replans=1,
        )
        == "end"
    )
    assert (
        route_from_critic(
            {"critic_verdict": {"decision": "manual_review_needed"}, "replan_count": 0},
            max_replans=1,
        )
        == "end"
    )


def test_supplement_graph_runs_end_to_end_to_awaiting_approval():
    async def fake_search_store(store_domain: str, query: str):
        return [
            _product(
                store_domain=store_domain,
                product_id="sleep-magnesium-{store}".format(store=store_domain.split(".")[0]),
                title="Magnesium Glycinate Night Support",
                price=32.0 if store_domain == "ritual.com" else 28.0,
                description=(
                    "Chelated magnesium glycinate for sleep support. "
                    "200 mg magnesium per serving. 30 servings."
                ),
            )
        ]

    async def fake_update_cart(store_domain: str, variant_id: str, quantity: int, *, cart_id=None):
        resolved_cart_id = cart_id or "{store_domain}-cart".format(store_domain=store_domain)
        return StoreCart(
            store_domain=store_domain,
            cart_id=resolved_cart_id,
            checkout_url="https://{store_domain}/cart/{cart_id}".format(
                store_domain=store_domain,
                cart_id=resolved_cart_id,
            ),
            total_quantity=quantity,
            subtotal_amount=28.0 * quantity,
            total_amount=28.0 * quantity,
            currency="USD",
            lines=[
                StoreCartLine(
                    line_id="line-1",
                    product_id="product-{variant_id}".format(variant_id=variant_id),
                    product_title="Product {variant_id}".format(variant_id=variant_id),
                    variant_id=variant_id,
                    variant_title="Default Title",
                    quantity=quantity,
                    subtotal_amount=28.0 * quantity,
                    total_amount=28.0 * quantity,
                    currency="USD",
                )
            ],
            errors=[],
            instructions="Open the checkout URL to complete purchase.",
        )

    graph = build_supplement_graph(
        settings=_settings(),
        search_store_fn=fake_search_store,
        update_cart_fn=fake_update_cart,
        store_domains=("ritual.com", "livemomentous.com"),
    )
    initial_state = SupplementStateSnapshot.starting(
        run_id="supp-run-123",
        user_id="user-123",
        health_profile=_health_profile().model_dump(mode="json"),
    ).model_dump(mode="json")

    async def run_test() -> None:
        captured_events = []

        async def emitter(event) -> None:
            captured_events.append(event)

        result = await invoke_supplement_graph(
            graph=graph,
            state=initial_state,
            settings=_settings(),
            source="api",
            event_emitter=emitter,
        )

        verdict = SupplementCriticVerdict.model_validate(result["critic_verdict"])
        assert result["status"] == "awaiting_approval"
        assert result["current_phase"] == "checkout"
        assert result["phase_statuses"]["checkout"] == "completed"
        assert len(result["identified_needs"]) == 1
        assert len(result["product_comparisons"]) == 1
        assert len(result["store_carts"]) == 1
        assert verdict.decision == "passed"
        assert result["trace_metadata"]["kind"] == "local"
        assert [event.event_type for event in captured_events].count("approval_requested") == 1
        assert any(event.event_type == "phase_started" and event.phase == "discovery" for event in captured_events)
        assert any(event.event_type == "phase_completed" and event.phase == "checkout" for event in captured_events)

    asyncio.run(run_test())


def test_supplement_graph_stops_for_manual_review():
    async def fake_search_store(store_domain: str, query: str):
        return [
            _product(
                store_domain=store_domain,
                product_id="sleep-magnesium",
                title="Magnesium Glycinate Night Support",
                price=28.0,
                description="Chelated magnesium glycinate. 200 mg magnesium per serving. 30 servings.",
            )
        ]

    async def fake_update_cart(store_domain: str, variant_id: str, quantity: int, *, cart_id=None):
        raise AssertionError("Checkout should not run when manual review is needed.")

    graph = build_supplement_graph(
        settings=_settings(),
        search_store_fn=fake_search_store,
        update_cart_fn=fake_update_cart,
        store_domains=("ritual.com",),
    )
    initial_state = SupplementStateSnapshot.starting(
        run_id="supp-run-456",
        user_id="user-456",
        health_profile=_health_profile(medications=["Sertraline"]).model_dump(mode="json"),
    ).model_dump(mode="json")

    result = asyncio.run(
        invoke_supplement_graph(
            graph=graph,
            state=initial_state,
            settings=_settings(),
            source="api",
        )
    )

    verdict = SupplementCriticVerdict.model_validate(result["critic_verdict"])
    assert result["status"] == "completed"
    assert result["current_phase"] == "analysis"
    assert result["store_carts"] == []
    assert verdict.decision == "manual_review_needed"
