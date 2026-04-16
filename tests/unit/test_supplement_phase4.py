from __future__ import annotations

import asyncio
import inspect

from shopper.agents.tools.browser_tools import BrowserCheckoutAgent
from shopper.config import Settings
from shopper.db import create_engine, create_session_factory, init_db
from shopper.schemas import OrderConfirmation
from shopper.supplements.models import SupplementBuyerProfile, SupplementRun
from shopper.supplements.schemas import (
    AgentCheckoutStartRequest,
    HealthProfile,
    PaymentCredentials,
    ShippingAddress,
    SupplementPhaseStatuses,
    ShopifyPriceRange,
    ShopifyProduct,
    ShopifyProductVariant,
    StackItem,
    StoreCart,
    StoreCartLine,
    StoreCartQuantityUpdate,
    SupplementCartUpdateRequest,
    SupplementRunApproveRequest,
    SupplementBuyerProfileUpsertRequest,
    SupplementCheckoutStartRequest,
    SupplementCheckoutContinueRequest,
    SupplementStack,
    SupplementStateSnapshot,
)
from shopper.supplements.services import CheckoutEmbedProbeResult, SupplementRunEventBus, SupplementRunManager


def _settings(database_url: str) -> Settings:
    return Settings(
        SHOPPER_DATABASE_URL=database_url,
        SHOPPER_APP_ENV="test",
        LANGSMITH_TRACING=False,
    )


def _health_profile() -> HealthProfile:
    return HealthProfile(
        age=34,
        weight_lbs=175,
        sex="male",
        health_goals=["better sleep"],
        current_supplements=[],
        medications=[],
        conditions=[],
        allergies=[],
        monthly_budget=100,
    )


def _product(store_domain: str, product_id: str, price: float) -> ShopifyProduct:
    return ShopifyProduct(
        store_domain=store_domain,
        product_id=product_id,
        title="Magnesium Glycinate",
        description="200 mg magnesium glycinate. 30 servings.",
        url="https://{store}/products/{product}".format(store=store_domain, product=product_id),
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


def _awaiting_approval_snapshot() -> SupplementStateSnapshot:
    product = _product("ritual.com", "magnesium-glycinate", 28.0)
    return SupplementStateSnapshot.starting(
        run_id="supp-run-approve",
        user_id="supp-user",
        health_profile=_health_profile(),
    ).model_copy(
        update={
            "recommended_stack": SupplementStack(
                summary="Night support stack.",
                items=[
                    StackItem(
                        category="magnesium",
                        goal="better sleep",
                        product=product,
                        quantity=1,
                        dosage="1 serving nightly",
                        cadence="nightly",
                        monthly_cost=28.0,
                        rationale="Supports relaxation before bed.",
                    )
                ],
                total_monthly_cost=28.0,
                currency="USD",
                within_budget=True,
                notes=[],
                warnings=[],
            ),
            "store_carts": [
                StoreCart(
                    store_domain="ritual.com",
                    cart_id="ritual-cart",
                    checkout_url="https://ritual.com/cart/ritual-cart",
                    total_quantity=1,
                    subtotal_amount=28.0,
                    total_amount=28.0,
                    currency="USD",
                    lines=[
                        StoreCartLine(
                            line_id="line-1",
                            product_id=product.product_id,
                            product_title=product.title,
                            variant_id=product.variants[0].variant_id,
                            variant_title=product.variants[0].title,
                            quantity=1,
                            subtotal_amount=28.0,
                            total_amount=28.0,
                            currency="USD",
                        )
                    ],
                    errors=[],
                    instructions="Open the checkout URL to complete purchase.",
                )
            ],
            "status": "awaiting_approval",
            "current_phase": "checkout",
            "current_node": "checkout_subgraph",
            "phase_statuses": SupplementPhaseStatuses(
                memory="completed",
                discovery="completed",
                analysis="completed",
                checkout="completed",
            ),
        }
        )


def _buyer_profile_request() -> SupplementBuyerProfileUpsertRequest:
    return SupplementBuyerProfileUpsertRequest(
        email="buyer@example.com",
        shipping_name="Buyer Example",
        shipping_address=ShippingAddress(
            line1="123 Main St",
            city="San Francisco",
            state="CA",
            postal_code="94105",
            country_code="US",
        ),
        consent_granted=True,
        max_order_total=120,
        max_monthly_total=240,
    )


def _payment_credentials() -> PaymentCredentials:
    return PaymentCredentials(
        card_number="4242424242424242",
        card_expiry="12/30",
        card_cvv="123",
        card_name="Buyer Example",
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
        await asyncio.sleep(0.01)
        return OrderConfirmation(
            confirmation_id="supp-confirm-123",
            total_cost=order.total_cost,
            confirmation_url=order.checkout_url,
            message="Browser agent placed the order.",
        )


def test_supplement_approve_request_normalizes_store_domains():
    payload = SupplementRunApproveRequest(approved_store_domains=[" Ritual.com ", "", "ritual.com", "LIVEMOMENTOUS.COM"])

    assert payload.approved_store_domains == ["ritual.com", "livemomentous.com"]


def test_supplement_run_manager_approve_run_persists_completion_and_events(tmp_path):
    database_url = "sqlite+aiosqlite:///{path}".format(path=tmp_path / "supplement-phase4.db")

    async def run_test() -> None:
        settings = _settings(database_url)
        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
        await init_db(engine)

        snapshot = _awaiting_approval_snapshot()
        async with session_factory() as session:
            session.add(
                SupplementRun(
                    run_id=snapshot.run_id,
                    user_id=snapshot.user_id,
                    status=snapshot.status,
                    state_snapshot=snapshot.model_dump(mode="json"),
                )
            )
            await session.commit()

        event_bus = SupplementRunEventBus()
        manager = SupplementRunManager(
            session_factory=session_factory,
            graph=None,
            settings=settings,
            event_bus=event_bus,
        )

        approved_run = await manager.approve_run(snapshot.run_id, approved_store_domains=["ritual.com"])
        assert approved_run.status == "running"

        async with session_factory() as session:
            stored_run = await session.get(SupplementRun, snapshot.run_id)
            assert stored_run is not None
            stored_snapshot = SupplementStateSnapshot.model_validate(stored_run.state_snapshot)
            assert stored_snapshot.status == "running"
            assert stored_snapshot.approved_store_domains == ["ritual.com"]
            assert stored_snapshot.current_node == "buyer_profile_gate"

        events = event_bus.list_events(snapshot.run_id)
        assert [event.event_type for event in events] == ["approval_resolved"]

        await engine.dispose()

    asyncio.run(run_test())


def test_supplement_run_manager_checkout_flow_completes_after_order_confirmation(tmp_path):
    database_url = "sqlite+aiosqlite:///{path}".format(path=tmp_path / "supplement-checkout.db")

    async def run_test() -> None:
        settings = _settings(database_url)
        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
        await init_db(engine)

        snapshot = _awaiting_approval_snapshot()
        async with session_factory() as session:
            session.add(
                SupplementRun(
                    run_id=snapshot.run_id,
                    user_id=snapshot.user_id,
                    status=snapshot.status,
                    state_snapshot=snapshot.model_dump(mode="json"),
                )
            )
            session.add(
                SupplementBuyerProfile(
                    user_id=snapshot.user_id,
                    email="buyer@example.com",
                    shipping_name="Buyer Example",
                    shipping_address_json={
                        "line1": "123 Main St",
                        "city": "San Francisco",
                        "state": "CA",
                        "postal_code": "94105",
                        "country_code": "US",
                    },
                    consent_granted=True,
                    max_order_total=120,
                    max_monthly_total=240,
                )
            )
            await session.commit()

        event_bus = SupplementRunEventBus()
        manager = SupplementRunManager(
            session_factory=session_factory,
            graph=None,
            settings=settings,
            event_bus=event_bus,
        )

        await manager.approve_stores(snapshot.run_id, approved_store_domains=["ritual.com"])
        started_run = await manager.start_checkout(snapshot.run_id, SupplementCheckoutStartRequest())
        assert started_run.status == "running"

        completed_run = await manager.continue_checkout(
            snapshot.run_id,
            "ritual.com",
            SupplementCheckoutContinueRequest(action="mark_order_placed"),
        )
        assert completed_run.status == "completed"

        async with session_factory() as session:
            stored_run = await session.get(SupplementRun, snapshot.run_id)
            assert stored_run is not None
            stored_snapshot = SupplementStateSnapshot.model_validate(stored_run.state_snapshot)
            assert stored_snapshot.checkout_sessions
            assert stored_snapshot.order_confirmations
            assert stored_snapshot.current_node == "order_confirmation"

        events = event_bus.list_events(snapshot.run_id)
        assert [event.event_type for event in events] == ["approval_resolved", "run_completed"]

        await engine.dispose()

    asyncio.run(run_test())


def test_supplement_run_manager_start_agent_checkout_places_order(tmp_path):
    database_url = "sqlite+aiosqlite:///{path}".format(path=tmp_path / "supplement-agent-checkout.db")

    async def run_test() -> None:
        settings = _settings(database_url)
        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
        await init_db(engine)

        snapshot = _awaiting_approval_snapshot()
        async with session_factory() as session:
            session.add(
                SupplementRun(
                    run_id=snapshot.run_id,
                    user_id=snapshot.user_id,
                    status=snapshot.status,
                    state_snapshot=snapshot.model_dump(mode="json"),
                )
            )
            session.add(
                SupplementBuyerProfile(
                    user_id=snapshot.user_id,
                    email="buyer@example.com",
                    shipping_name="Buyer Example",
                    shipping_address_json={
                        "line1": "123 Main St",
                        "city": "San Francisco",
                        "state": "CA",
                        "postal_code": "94105",
                        "country_code": "US",
                    },
                    consent_granted=True,
                    max_order_total=120,
                    max_monthly_total=240,
                )
            )
            await session.commit()

        event_bus = SupplementRunEventBus()
        checkout_backend = FakeSupplementAgentCheckoutBackend()
        manager = SupplementRunManager(
            session_factory=session_factory,
            graph=None,
            settings=settings,
            event_bus=event_bus,
            checkout_agent=BrowserCheckoutAgent(
                settings,
                automation_backend=checkout_backend,
                artifact_root=tmp_path / "artifacts",
            ),
        )

        await manager.approve_stores(snapshot.run_id, approved_store_domains=["ritual.com"])
        started_run = await manager.start_agent_checkout(
            snapshot.run_id,
            AgentCheckoutStartRequest(payment_credentials=_payment_credentials()),
        )
        started_snapshot = SupplementStateSnapshot.model_validate(started_run.state_snapshot)

        assert started_run.status == "running"
        assert started_snapshot.checkout_sessions
        assert started_snapshot.checkout_sessions[0].presentation_mode == "agent"
        assert started_snapshot.checkout_sessions[0].status == "agent_running"

        task = manager._checkout_tasks[snapshot.run_id]
        await asyncio.wait_for(task, timeout=2.0)

        async with session_factory() as session:
            stored_run = await session.get(SupplementRun, snapshot.run_id)
            assert stored_run is not None
            stored_snapshot = SupplementStateSnapshot.model_validate(stored_run.state_snapshot)
            assert stored_run.status == "completed"
            assert stored_snapshot.checkout_sessions[0].status == "order_placed"
            assert stored_snapshot.checkout_sessions[0].presentation_mode == "agent"
            assert (
                stored_snapshot.checkout_sessions[0].embedded_state_payload["agent_live_url"]
                == "https://live.browser-use.com/fake-supplement"
            )
            assert stored_snapshot.order_confirmations
            assert stored_snapshot.current_node == "order_confirmation"

        assert checkout_backend.task_overrides
        assert "Card number: 4242424242424242" in (checkout_backend.task_overrides[0] or "")
        assert "Email: buyer@example.com" in (checkout_backend.task_overrides[0] or "")

        events = event_bus.list_events(snapshot.run_id)
        assert [event.event_type for event in events] == [
            "approval_resolved",
            "node_entered",
            "node_entered",
            "node_completed",
            "run_completed",
        ]

        await engine.dispose()

    asyncio.run(run_test())


def test_supplement_run_manager_updates_cart_quantities(tmp_path):
    database_url = "sqlite+aiosqlite:///{path}".format(path=tmp_path / "supplement-cart-edit.db")

    async def run_test() -> None:
        settings = _settings(database_url)
        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
        await init_db(engine)

        snapshot = _awaiting_approval_snapshot()
        async with session_factory() as session:
            session.add(
                SupplementRun(
                    run_id=snapshot.run_id,
                    user_id=snapshot.user_id,
                    status=snapshot.status,
                    state_snapshot=snapshot.model_dump(mode="json"),
                )
            )
            await session.commit()

        manager = SupplementRunManager(
            session_factory=session_factory,
            graph=None,
            settings=settings,
            event_bus=SupplementRunEventBus(),
            checkout_agent=BrowserCheckoutAgent(
                settings,
                automation_backend=FakeSupplementAgentCheckoutBackend(),
                artifact_root=tmp_path / "artifacts",
            ),
        )
        updated_run = await manager.update_cart_quantities(
            snapshot.run_id,
            SupplementCartUpdateRequest(
                updates=[
                    StoreCartQuantityUpdate(
                        store_domain="ritual.com",
                        line_id="line-1",
                        quantity=3,
                    )
                ]
            ),
        )

        updated_snapshot = SupplementStateSnapshot.model_validate(updated_run.state_snapshot)
        updated_cart = updated_snapshot.store_carts[0]
        assert updated_cart.total_quantity == 3
        assert updated_cart.subtotal_amount == 84.0
        assert updated_cart.total_amount == 84.0
        assert updated_cart.lines[0].quantity == 3
        assert updated_cart.lines[0].total_amount == 84.0
        assert updated_snapshot.recommended_stack is not None
        assert updated_snapshot.recommended_stack.items[0].quantity == 3
        assert updated_snapshot.recommended_stack.total_monthly_cost == 84.0

        await engine.dispose()

    asyncio.run(run_test())


def test_supplement_run_manager_auto_mode_uses_external_handoff_when_probe_blocks_embed(tmp_path):
    database_url = "sqlite+aiosqlite:///{path}".format(path=tmp_path / "supplement-embed-mode.db")

    class BlockingEmbedProbeService:
        async def probe_checkout_url(self, checkout_url: str) -> CheckoutEmbedProbeResult:
            return CheckoutEmbedProbeResult(
                checkout_url=checkout_url,
                final_url=checkout_url,
                status_code=200,
                iframe_allowed=False,
                block_reason="Merchant CSP frame-ancestors does not allow Shopper origins.",
                x_frame_options=None,
                content_security_policy="frame-ancestors 'self'",
                frame_ancestors=["'self'"],
                allowed_embed_origins=["http://localhost:3000"],
            )

    async def run_test() -> None:
        settings = _settings(database_url)
        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
        await init_db(engine)

        snapshot = _awaiting_approval_snapshot()
        async with session_factory() as session:
            session.add(
                SupplementRun(
                    run_id=snapshot.run_id,
                    user_id=snapshot.user_id,
                    status=snapshot.status,
                    state_snapshot=snapshot.model_dump(mode="json"),
                )
            )
            session.add(
                SupplementBuyerProfile(
                    user_id=snapshot.user_id,
                    email="buyer@example.com",
                    shipping_name="Buyer Example",
                    shipping_address_json={
                        "line1": "123 Main St",
                        "city": "San Francisco",
                        "state": "CA",
                        "postal_code": "94105",
                        "country_code": "US",
                    },
                    consent_granted=True,
                )
            )
            await session.commit()

        event_bus = SupplementRunEventBus()
        manager = SupplementRunManager(
            session_factory=session_factory,
            graph=None,
            settings=settings,
            event_bus=event_bus,
        )
        manager.embedded_checkout_orchestrator.embed_probe_service = BlockingEmbedProbeService()

        await manager.approve_stores(snapshot.run_id, approved_store_domains=["ritual.com"])
        started_run = await manager.start_checkout(snapshot.run_id, SupplementCheckoutStartRequest())
        started_snapshot = SupplementStateSnapshot.model_validate(started_run.state_snapshot)

        assert started_snapshot.checkout_sessions
        assert started_snapshot.checkout_sessions[0].presentation_mode == "external"
        assert started_snapshot.checkout_sessions[0].status == "external_handoff"
        assert started_snapshot.checkout_sessions[0].error_message == "Merchant CSP frame-ancestors does not allow Shopper origins."

        await engine.dispose()

    asyncio.run(run_test())
