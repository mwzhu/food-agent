from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shopper.agents.tools.browser_tools import CheckoutAutomationBackend, CheckoutFlowError
from shopper.config import Settings
from shopper.schemas import CartLineItem, CheckoutStoreConfig, PurchaseOrder, StandaloneCheckoutRequest
from shopper.supplements.models import SupplementCheckoutSession, SupplementRun
from shopper.supplements.schemas import (
    PaymentCredentials,
    StoreCart,
    SupplementBuyerProfileRead,
    SupplementBuyerProfileSnapshot,
    SupplementCheckoutSessionRead,
    SupplementOrderConfirmation,
    SupplementOrderConfirmationLine,
    SupplementRunEvent,
    SupplementStateSnapshot,
)
from shopper.supplements.services.embedded_checkout_orchestrator import checkout_session_to_read


class AgentCheckoutOrchestrator:
    def __init__(
        self,
        settings: Settings,
        *,
        checkout_backend: CheckoutAutomationBackend,
        artifact_root: Path,
    ) -> None:
        self.settings = settings
        self.checkout_backend = checkout_backend
        self.artifact_root = artifact_root

    async def execute_agent_checkout(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        run_id: str,
        store_carts: list[StoreCart],
        approved_store_domains: list[str],
        buyer_profile: SupplementBuyerProfileRead,
        payment_credentials: PaymentCredentials,
        simulate_success: bool = False,
        event_emitter: Callable[[SupplementRunEvent], Awaitable[None]],
        settings: Settings,
    ) -> None:
        cart_by_domain = {cart.store_domain.lower(): cart for cart in store_carts if cart.checkout_url}
        parallelism = min(len(approved_store_domains) or 1, settings.browser_checkout_parallel_stores)
        semaphore = asyncio.Semaphore(max(1, parallelism))

        async def run_store(store_domain: str) -> None:
            async with semaphore:
                await self._execute_single_store_checkout(
                    session_factory=session_factory,
                    run_id=run_id,
                    store_domain=store_domain,
                    cart=cart_by_domain.get(store_domain.lower()),
                    buyer_profile=buyer_profile,
                    payment_credentials=payment_credentials,
                    simulate_success=simulate_success,
                    event_emitter=event_emitter,
                    settings=settings,
                )

        await asyncio.gather(*(run_store(store_domain) for store_domain in approved_store_domains))

    async def _execute_single_store_checkout(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        run_id: str,
        store_domain: str,
        cart: StoreCart | None,
        buyer_profile: SupplementBuyerProfileRead,
        payment_credentials: PaymentCredentials,
        simulate_success: bool,
        event_emitter: Callable[[SupplementRunEvent], Awaitable[None]],
        settings: Settings,
    ) -> None:
        if cart is None or not cart.checkout_url:
            await self._mark_session_failed(
                session_factory=session_factory,
                run_id=run_id,
                store_domain=store_domain,
                buyer_profile=buyer_profile,
                error_code="checkout_navigation_failed",
                error_message="Checkout URL is missing for this store.",
            )
            await event_emitter(
                SupplementRunEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    event_type="node_completed",
                    phase="checkout",
                    node_name="agent_checkout_orchestrator",
                    message=f"Could not start browser checkout for {store_domain} because the checkout URL is missing.",
                    data={"store_domain": store_domain, "status": "failed"},
                )
            )
            return

        current_session = await self._get_session_row(session_factory, run_id, store_domain)
        if current_session is None:
            return
        if current_session.status == "cancelled":
            await event_emitter(
                SupplementRunEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    event_type="node_completed",
                    phase="checkout",
                    node_name="agent_checkout_orchestrator",
                    message=f"Skipped {store_domain} before browser checkout started.",
                    data={"store_domain": store_domain, "status": "cancelled"},
                )
            )
            return

        view_mode = "cloud" if settings.browser_checkout_use_cloud else "local"
        await self._mark_session_running(
            session_factory=session_factory,
            run_id=run_id,
            store_domain=store_domain,
            buyer_profile=buyer_profile,
            status_text="Cloud browser checkout starting..." if view_mode == "cloud" else "Browser agent opening checkout window...",
            view_mode=view_mode,
        )
        await event_emitter(
            SupplementRunEvent(
                event_id=str(uuid4()),
                run_id=run_id,
                event_type="node_entered",
                phase="checkout",
                node_name="agent_checkout_orchestrator",
                message=f"Browser agent opening checkout for {store_domain}...",
                data={"store_domain": store_domain, "status": "agent_running", "view_mode": view_mode},
            )
        )

        async def handle_browser_status(payload: dict[str, object]) -> None:
            status_type = payload.get("type")
            if status_type == "browser_attempt":
                view_mode = str(payload.get("view_mode") or "cloud")
                status_text = str(payload.get("status_text") or "Browser agent is retrying checkout...")
                await self._mark_session_running(
                    session_factory=session_factory,
                    run_id=run_id,
                    store_domain=store_domain,
                    buyer_profile=buyer_profile,
                    status_text=status_text,
                    view_mode=view_mode,
                    clear_live_url=True,
                )
                await event_emitter(
                    SupplementRunEvent(
                        event_id=str(uuid4()),
                        run_id=run_id,
                        event_type="node_entered",
                        phase="checkout",
                        node_name="agent_checkout_orchestrator",
                        message=status_text,
                        data={
                            "store_domain": store_domain,
                            "status": "agent_running",
                            "view_mode": view_mode,
                            "attempt_label": payload.get("attempt_label"),
                        },
                    )
                )
                return

            if status_type != "browser_live_url":
                return
            live_url = str(payload.get("live_url") or "").strip()
            if not live_url:
                return
            cloud_browser_session_id = str(payload.get("cloud_browser_session_id") or "").strip() or None
            await self._mark_session_live(
                session_factory=session_factory,
                run_id=run_id,
                store_domain=store_domain,
                buyer_profile=buyer_profile,
                live_url=live_url,
                cloud_browser_session_id=cloud_browser_session_id,
            )
            await event_emitter(
                SupplementRunEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    event_type="node_entered",
                    phase="checkout",
                    node_name="agent_checkout_orchestrator",
                    message=f"Live browser view ready for {store_domain}.",
                    data={
                        "store_domain": store_domain,
                        "status": "agent_running",
                        "agent_live_url": live_url,
                    },
                )
            )

        request = self._build_request(cart, settings)
        order = self._build_order(run_id=run_id, cart=cart)
        task_prompt = self._build_checkout_task(
            cart=cart,
            checkout_url=cart.checkout_url,
            buyer_profile=buyer_profile,
            payment_credentials=payment_credentials,
            simulate_success=simulate_success,
        )

        try:
            confirmation = await self.checkout_backend.complete_checkout(
                request,
                order,
                self._artifact_dir(run_id, store_domain),
                task_override=task_prompt,
                status_callback=handle_browser_status,
            )
        except CheckoutFlowError as exc:
            await self._mark_session_failed(
                session_factory=session_factory,
                run_id=run_id,
                store_domain=store_domain,
                buyer_profile=buyer_profile,
                error_code=exc.code,
                error_message=str(exc),
            )
            await event_emitter(
                SupplementRunEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    event_type="node_completed",
                    phase="checkout",
                    node_name="agent_checkout_orchestrator",
                    message=f"Browser agent could not place the order at {store_domain}: {exc}",
                    data={"store_domain": store_domain, "status": "failed", "error_code": exc.code},
                )
            )
            return
        except Exception as exc:
            error_code = _checkout_error_code_for_exception(exc)
            await self._mark_session_failed(
                session_factory=session_factory,
                run_id=run_id,
                store_domain=store_domain,
                buyer_profile=buyer_profile,
                error_code=error_code,
                error_message=str(exc),
            )
            await event_emitter(
                SupplementRunEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    event_type="node_completed",
                    phase="checkout",
                    node_name="agent_checkout_orchestrator",
                    message=f"Browser agent hit an unexpected error at {store_domain}: {exc}",
                    data={"store_domain": store_domain, "status": "failed", "error_code": error_code},
                )
            )
            return

        await self._mark_session_complete(
            session_factory=session_factory,
            run_id=run_id,
            store_domain=store_domain,
            buyer_profile=buyer_profile,
            confirmation=SupplementOrderConfirmation(
                confirmation_id=confirmation.confirmation_id,
                store_domain=store_domain,
                message=confirmation.message or "Browser agent placed the order and synced the confirmation.",
                order_total=confirmation.total_cost,
                currency=cart.currency,
                confirmation_url=confirmation.confirmation_url or cart.checkout_url or _store_home_url(cart.store_domain),
                line_items=_confirmation_line_items(cart),
            ),
        )
        await event_emitter(
            SupplementRunEvent(
                event_id=str(uuid4()),
                run_id=run_id,
                event_type="node_completed",
                phase="checkout",
                node_name="agent_checkout_orchestrator",
                message=f"Browser agent placed the order at {store_domain}.",
                data={"store_domain": store_domain, "status": "order_placed"},
            )
        )

    def _artifact_dir(self, run_id: str, store_domain: str) -> Path:
        safe_store = store_domain.replace("/", "-")
        artifact_dir = self.artifact_root / "supplements" / run_id / safe_store
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return artifact_dir

    def _build_request(self, cart: StoreCart, settings: Settings) -> StandaloneCheckoutRequest:
        checkout_host = (urlparse(cart.checkout_url or "").hostname or "").lower()
        allowed_domains = [domain for domain in dict.fromkeys([cart.store_domain.lower(), checkout_host]) if domain]
        return StandaloneCheckoutRequest(
            user_id="supplement-agent",
            store=CheckoutStoreConfig(
                store=cart.store_domain,
                start_url=_store_home_url(cart.store_domain),
                checkout_url=cart.checkout_url,
                allowed_domains=allowed_domains,
            ),
            items=[],
            approve=True,
            headless=False,
            max_steps=settings.browser_checkout_max_steps,
        )

    def _build_order(self, *, run_id: str, cart: StoreCart) -> PurchaseOrder:
        return PurchaseOrder(
            order_id=f"{run_id}-{uuid4().hex[:8]}",
            store=cart.store_domain,
            store_url=_store_home_url(cart.store_domain),
            status="approved",
            items=[
                CartLineItem(
                    requested_name=line.product_title,
                    requested_quantity=float(line.quantity),
                    actual_name=line.product_title,
                    actual_quantity=float(line.quantity),
                    unit_price=(line.total_amount or line.subtotal_amount or 0) / max(line.quantity, 1),
                    line_total=line.total_amount or line.subtotal_amount or 0,
                    status="added",
                )
                for line in cart.lines
            ],
            subtotal=cart.subtotal_amount or 0,
            total_cost=cart.total_amount or cart.subtotal_amount or 0,
            checkout_url=cart.checkout_url,
            allowed_domains=[cart.store_domain],
        )

    @staticmethod
    def _build_checkout_task(
        *,
        cart: StoreCart,
        checkout_url: str,
        buyer_profile: SupplementBuyerProfileRead,
        payment_credentials: PaymentCredentials,
        simulate_success: bool = False,
    ) -> str:
        address = buyer_profile.shipping_address
        item_lines = "\n".join(
            "- {title}; variant: {variant}; quantity: {quantity}".format(
                title=line.product_title,
                variant=line.variant_title or "Default Title",
                quantity=line.quantity,
            )
            for line in cart.lines
        )
        fallback_url = _store_home_url(cart.store_domain)
        simulation_instructions = ""
        if simulate_success:
            simulation_instructions = (
                "\nSIMULATION MODE IS ENABLED.\n"
                "Fill shipping and payment details only as far as needed to reach the final review or final payment step.\n"
                "Do NOT click any final button that submits, pays, places, confirms, or charges the order.\n"
                "When the checkout is ready for the final payment/place-order click, stop and return structured output as if the payment succeeded.\n"
                f"Use confirmation_id='SIMULATED-{cart.store_domain}-{uuid4().hex[:8]}'.\n"
                f"Use total_cost={cart.total_amount or cart.subtotal_amount or 0}.\n"
                "Set status='confirmed' and message='Simulated payment success for demo checkout; no real order was placed.'.\n"
            )
        return (
            f"Complete checkout at {checkout_url} for a supplement order.\n"
            f"If that cart or checkout URL is unreachable, expired, empty, or redirects to a storefront page, go to {fallback_url} and rebuild the cart with these exact items before checking out:\n"
            f"{item_lines}\n"
            "Before entering payment or placing the order, verify the cart contains exactly the item names, variants, and quantities listed above. If the merchant cart has different quantities, update the cart to match the list above before continuing.\n"
            "Do not substitute products unless the exact item is unavailable; if unavailable, return status='failed' with failure_code='cart_verification_failed'.\n"
            "Fill in the following shipping information:\n"
            f"- Email: {buyer_profile.email}\n"
            f"- Name: {buyer_profile.shipping_name}\n"
            f"- Address: {address.line1}, {address.city}, {address.state} {address.postal_code}, {address.country_code}\n"
            "Use the following payment card:\n"
            f"- Card number: {payment_credentials.card_number}\n"
            f"- Expiry: {payment_credentials.card_expiry}\n"
            f"- CVV: {payment_credentials.card_cvv}\n"
            f"- Name on card: {payment_credentials.card_name}\n"
            f"{simulation_instructions}"
            f"{'Do not place the real order. Return structured output only.' if simulate_success else 'Place the order. Return structured output only.'}\n"
            "If confirmed, set status='confirmed'.\n"
            "If checkout fails, set status='failed' with failure_reason and failure_code."
        )

    async def _get_session_row(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        run_id: str,
        store_domain: str,
    ) -> SupplementCheckoutSession | None:
        async with session_factory() as session:
            return await session.scalar(
                select(SupplementCheckoutSession).where(
                    SupplementCheckoutSession.run_id == run_id,
                    SupplementCheckoutSession.store_domain == store_domain,
                )
            )

    async def _mark_session_running(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        run_id: str,
        store_domain: str,
        buyer_profile: SupplementBuyerProfileRead,
        status_text: str,
        view_mode: str,
        clear_live_url: bool = False,
    ) -> None:
        async with session_factory() as session:
            checkout_row = await self._require_session_row(session, run_id, store_domain)
            checkout_row.status = "agent_running"
            checkout_row.error_code = None
            checkout_row.error_message = None
            payload = dict(checkout_row.embedded_state_payload or {})
            payload["agent_status_text"] = status_text
            payload["agent_step"] = "running"
            payload["agent_view_mode"] = view_mode
            if clear_live_url:
                payload.pop("agent_live_url", None)
                payload.pop("cloud_browser_session_id", None)
            checkout_row.embedded_state_payload = payload
            await self._sync_run_snapshot(
                session,
                run_id=run_id,
                buyer_profile=buyer_profile,
                status="running",
                current_node="agent_checkout_orchestrator",
                active_store_domain=store_domain,
            )
            await session.commit()

    async def _mark_session_live(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        run_id: str,
        store_domain: str,
        buyer_profile: SupplementBuyerProfileRead,
        live_url: str,
        cloud_browser_session_id: str | None,
    ) -> None:
        async with session_factory() as session:
            checkout_row = await self._require_session_row(session, run_id, store_domain)
            if checkout_row.status != "agent_running":
                return

            payload = dict(checkout_row.embedded_state_payload or {})
            payload["agent_live_url"] = live_url
            payload["agent_view_mode"] = "cloud"
            payload["agent_status_text"] = "Live cloud browser connected. The agent is working through checkout."
            payload["agent_step"] = "live"
            if cloud_browser_session_id:
                payload["cloud_browser_session_id"] = cloud_browser_session_id
            checkout_row.embedded_state_payload = payload
            await self._sync_run_snapshot(
                session,
                run_id=run_id,
                buyer_profile=buyer_profile,
                status="running",
                current_node="agent_checkout_orchestrator",
                active_store_domain=store_domain,
            )
            await session.commit()

    async def _mark_session_complete(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        run_id: str,
        store_domain: str,
        buyer_profile: SupplementBuyerProfileRead,
        confirmation: SupplementOrderConfirmation,
    ) -> None:
        async with session_factory() as session:
            checkout_row = await self._require_session_row(session, run_id, store_domain)
            checkout_row.status = "order_placed"
            checkout_row.order_confirmation_json = confirmation.model_dump(mode="json")
            checkout_row.error_code = None
            checkout_row.error_message = None
            payload = dict(checkout_row.embedded_state_payload or {})
            payload["agent_status_text"] = "Order placed!"
            payload["agent_step"] = "completed"
            checkout_row.embedded_state_payload = payload
            await self._sync_run_snapshot(
                session,
                run_id=run_id,
                buyer_profile=buyer_profile,
                status="running",
                current_node="agent_checkout_orchestrator",
                active_store_domain=store_domain,
            )
            await session.commit()

    async def _mark_session_failed(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        run_id: str,
        store_domain: str,
        buyer_profile: SupplementBuyerProfileRead,
        error_code: str,
        error_message: str,
    ) -> None:
        async with session_factory() as session:
            checkout_row = await self._require_session_row(session, run_id, store_domain)
            checkout_row.status = "failed"
            checkout_row.error_code = error_code
            checkout_row.error_message = error_message
            payload = dict(checkout_row.embedded_state_payload or {})
            payload["agent_status_text"] = "Checkout failed."
            payload["agent_step"] = "failed"
            checkout_row.embedded_state_payload = payload
            await self._sync_run_snapshot(
                session,
                run_id=run_id,
                buyer_profile=buyer_profile,
                status="running",
                current_node="agent_checkout_orchestrator",
                active_store_domain=store_domain,
                latest_error=error_message,
            )
            await session.commit()

    async def _require_session_row(
        self,
        session: AsyncSession,
        run_id: str,
        store_domain: str,
    ) -> SupplementCheckoutSession:
        checkout_row = await session.scalar(
            select(SupplementCheckoutSession).where(
                SupplementCheckoutSession.run_id == run_id,
                SupplementCheckoutSession.store_domain == store_domain,
            )
        )
        if checkout_row is None:
            raise LookupError("Checkout session not found.")
        return checkout_row

    async def _sync_run_snapshot(
        self,
        session: AsyncSession,
        *,
        run_id: str,
        buyer_profile: SupplementBuyerProfileRead,
        status: str,
        current_node: str,
        active_store_domain: str | None = None,
        latest_error: str | None = None,
    ) -> None:
        supplement_run = await session.get(SupplementRun, run_id)
        if supplement_run is None:
            return

        snapshot = SupplementStateSnapshot.model_validate(supplement_run.state_snapshot)
        checkout_sessions = await _list_checkout_sessions(session, run_id)
        active_session = next((checkout_session for checkout_session in checkout_sessions if not checkout_session.is_terminal), None)
        continue_url = active_session.continue_url if active_session else None
        payment_handlers = active_session.payment_handlers if active_session else []

        updated_snapshot = snapshot.model_copy(
            update={
                "buyer_profile": SupplementBuyerProfileSnapshot.from_profile(buyer_profile),
                "buyer_profile_ready": buyer_profile.is_ready,
                "checkout_sessions": checkout_sessions,
                "active_checkout_store": active_store_domain or (active_session.store_domain if active_session else None),
                "continue_url": continue_url,
                "payment_handlers": payment_handlers,
                "order_confirmations": [
                    checkout_session.order_confirmation
                    for checkout_session in checkout_sessions
                    if checkout_session.order_confirmation
                ],
                "fallback_reason": None,
                "status": status,
                "current_phase": "checkout",
                "current_node": current_node,
                "latest_error": latest_error or _latest_checkout_error(checkout_sessions),
            }
        )

        supplement_run.status = status
        supplement_run.state_snapshot = jsonable_encoder(updated_snapshot.model_dump(mode="json"))


async def _list_checkout_sessions(session: AsyncSession, run_id: str) -> list[SupplementCheckoutSessionRead]:
    rows = await session.scalars(
        select(SupplementCheckoutSession)
        .where(SupplementCheckoutSession.run_id == run_id)
        .order_by(SupplementCheckoutSession.store_domain.asc())
    )
    return [checkout_session_to_read(row) for row in rows]


def _latest_checkout_error(checkout_sessions: list[SupplementCheckoutSessionRead]) -> str | None:
    for checkout_session in checkout_sessions:
        if checkout_session.error_message:
            return checkout_session.error_message
    return None


def _checkout_error_code_for_exception(exc: Exception) -> str:
    lowered = str(exc).lower()
    if "err_tunnel_connection_failed" in lowered or "navigation failed" in lowered:
        return "checkout_navigation_failed"
    if "captcha" in lowered or "bot" in lowered:
        return "bot_protection"
    return "unknown"


def _confirmation_line_items(cart: StoreCart) -> list[SupplementOrderConfirmationLine]:
    return [
        SupplementOrderConfirmationLine(
            title=line.product_title,
            quantity=line.quantity,
            variant_title=line.variant_title or None,
            total_amount=line.total_amount or line.subtotal_amount,
            currency=line.currency or cart.currency,
        )
        for line in cart.lines
    ]


def _store_home_url(store_domain: str) -> str:
    parsed = urlparse(store_domain)
    if parsed.scheme and parsed.netloc:
        return store_domain
    return f"https://www.{store_domain.removeprefix('www.')}"
