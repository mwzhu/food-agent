from __future__ import annotations

import asyncio

from shopper.supplements.events import bind_event_emitter, emit_supplement_event
from shopper.supplements.schemas import HealthProfile, ShopifyProduct, StoreCart, SupplementStateSnapshot
from shopper.supplements.tools.shopify_mcp import (
    ShopifyCartLine as MCPShopifyCartLine,
    ShopifyCartResult as MCPShopifyCartResult,
    ShopifyPriceRange as MCPShopifyPriceRange,
    ShopifyProduct as MCPShopifyProduct,
    ShopifyProductVariant as MCPShopifyProductVariant,
)


def test_health_profile_normalizes_list_fields():
    profile = HealthProfile(
        age=34,
        weight_lbs=175,
        sex="male",
        health_goals=[" better sleep ", "better sleep", "", "muscle recovery"],
        current_supplements=["Creatine  ", "Creatine", " Vitamin D"],
        medications=["", "Metformin"],
        conditions=["  thyroid  "],
        allergies=[" soy ", "soy", None],
        monthly_budget=120,
    )

    assert profile.health_goals == ["better sleep", "muscle recovery"]
    assert profile.current_supplements == ["Creatine", "Vitamin D"]
    assert profile.medications == ["Metformin"]
    assert profile.conditions == ["thyroid"]
    assert profile.allergies == ["soy"]


def test_shopify_product_from_mcp_maps_price_and_variant_fields():
    mcp_product = MCPShopifyProduct(
        product_id="gid://shopify/Product/1",
        title="Magnesium L-Threonate",
        description="Sleep support",
        url="https://livemomentous.com/products/magnesium",
        image_url="https://cdn.example.com/magnesium.png",
        image_alt_text="Magnesium bottle",
        product_type="Supplement",
        tags=["sleep"],
        price_range=MCPShopifyPriceRange(min_price="49.95", max_price="49.95", currency="USD"),
        variants=[
            MCPShopifyProductVariant(
                variant_id="gid://shopify/ProductVariant/10",
                title="Default Title",
                price="49.95",
                currency="USD",
                available=True,
            )
        ],
    )

    product = ShopifyProduct.from_mcp(store_domain="livemomentous.com", product=mcp_product)

    assert product.store_domain == "livemomentous.com"
    assert product.price_range.min_price == 49.95
    assert product.default_variant is not None
    assert product.default_variant.variant_id == "gid://shopify/ProductVariant/10"


def test_store_cart_from_mcp_maps_amounts_and_lines():
    mcp_cart = MCPShopifyCartResult(
        store_domain="ritual.com",
        cart_id="gid://shopify/Cart/1?key=abc",
        checkout_url="https://ritual.com/cart/c/1?key=abc",
        created_at="2026-04-09T00:00:00Z",
        updated_at="2026-04-09T00:00:00Z",
        total_quantity=1,
        subtotal_amount="39.00",
        total_amount="39.00",
        currency="USD",
        lines=[
            MCPShopifyCartLine(
                line_id="gid://shopify/CartLine/1",
                quantity=1,
                product_title="Sleep BioSeries Melatonin",
                product_id="gid://shopify/Product/1",
                variant_id="gid://shopify/ProductVariant/2",
                variant_title="Default Title",
                subtotal_amount="39.00",
                total_amount="39.00",
                currency="USD",
            )
        ],
        errors=[],
        instructions="Use the checkout URL when ready.",
    )

    cart = StoreCart.from_mcp(mcp_cart)

    assert cart.subtotal_amount == 39.0
    assert cart.total_amount == 39.0
    assert cart.lines[0].product_title == "Sleep BioSeries Melatonin"
    assert cart.lines[0].quantity == 1


def test_supplement_snapshot_starting_and_failure_states():
    snapshot = SupplementStateSnapshot.starting(
        run_id="run-123",
        user_id="user-123",
        health_profile={
            "age": 29,
            "weight_lbs": 140,
            "sex": "female",
            "health_goals": ["better sleep"],
            "current_supplements": [],
            "medications": [],
            "conditions": [],
            "allergies": [],
            "monthly_budget": 80,
        },
    )

    failed = snapshot.model_copy(
        update={
            "current_phase": "analysis",
        }
    ).as_failed("comparison step failed")

    assert snapshot.status == "running"
    assert snapshot.current_phase == "memory"
    assert snapshot.phase_statuses.memory == "running"
    assert failed.status == "failed"
    assert failed.current_node == "error"
    assert failed.phase_statuses.discovery == "completed"
    assert failed.phase_statuses.analysis == "failed"


def test_emit_supplement_event_uses_bound_emitter():
    async def run_test() -> None:
        captured = []

        async def emitter(event) -> None:
            captured.append(event)

        with bind_event_emitter(emitter):
            await emit_supplement_event(
                run_id="run-456",
                event_type="phase_started",
                message="Discovery started",
                phase="discovery",
                node_name="store_searcher",
                data={"store_count": 3},
            )

        assert len(captured) == 1
        assert captured[0].run_id == "run-456"
        assert captured[0].phase == "discovery"
        assert captured[0].data == {"store_count": 3}

    asyncio.run(run_test())
