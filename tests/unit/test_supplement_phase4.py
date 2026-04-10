from __future__ import annotations

import asyncio

from shopper.config import Settings
from shopper.db import create_engine, create_session_factory, init_db
from shopper.supplements.models import SupplementRun
from shopper.supplements.schemas import (
    HealthProfile,
    SupplementPhaseStatuses,
    ShopifyPriceRange,
    ShopifyProduct,
    ShopifyProductVariant,
    StackItem,
    StoreCart,
    StoreCartLine,
    SupplementRunApproveRequest,
    SupplementStack,
    SupplementStateSnapshot,
)
from shopper.supplements.services import SupplementRunEventBus, SupplementRunManager


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
        assert approved_run.status == "completed"

        async with session_factory() as session:
            stored_run = await session.get(SupplementRun, snapshot.run_id)
            assert stored_run is not None
            stored_snapshot = SupplementStateSnapshot.model_validate(stored_run.state_snapshot)
            assert stored_snapshot.status == "completed"
            assert stored_snapshot.approved_store_domains == ["ritual.com"]
            assert stored_snapshot.current_node == "approval_gate"

        events = event_bus.list_events(snapshot.run_id)
        assert [event.event_type for event in events] == ["approval_resolved", "run_completed"]

        await engine.dispose()

    asyncio.run(run_test())
