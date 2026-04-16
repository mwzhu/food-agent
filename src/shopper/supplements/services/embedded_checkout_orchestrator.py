from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopper.config import Settings
from shopper.supplements.models import SupplementCheckoutSession
from shopper.supplements.schemas import (
    StoreCart,
    SupplementBuyerProfileRead,
    SupplementCheckoutCancelRequest,
    SupplementCheckoutContinueRequest,
    SupplementCheckoutSessionRead,
    SupplementOrderConfirmation,
)
from shopper.supplements.services.checkout_embed_probe import CheckoutEmbedProbeResult, CheckoutEmbedProbeService


class EmbeddedCheckoutOrchestrator:
    def __init__(
        self,
        settings: Settings,
        *,
        embed_probe_service: CheckoutEmbedProbeService | None = None,
    ) -> None:
        self.settings = settings
        self.embed_probe_service = embed_probe_service or CheckoutEmbedProbeService(settings)

    async def aclose(self) -> None:
        await self.embed_probe_service.aclose()

    async def prepare_sessions(
        self,
        *,
        session: AsyncSession,
        run_id: str,
        store_carts: list[StoreCart],
        approved_store_domains: list[str],
        buyer_profile: SupplementBuyerProfileRead,
    ) -> list[SupplementCheckoutSessionRead]:
        existing_rows = await session.scalars(
            select(SupplementCheckoutSession).where(SupplementCheckoutSession.run_id == run_id)
        )
        existing_by_domain = {row.store_domain.lower(): row for row in existing_rows}
        cart_by_domain = {cart.store_domain.lower(): cart for cart in store_carts}
        resolved_rows: list[SupplementCheckoutSession] = []

        for store_domain in approved_store_domains:
            cart = cart_by_domain.get(store_domain.lower())
            if cart is None:
                continue

            checkout_row = existing_by_domain.get(store_domain.lower())
            if checkout_row is None:
                checkout_row = SupplementCheckoutSession(
                    session_id=str(uuid4()),
                    run_id=run_id,
                    store_domain=store_domain,
                )
                session.add(checkout_row)

            embed_probe = await self._probe_checkout_mode(cart)
            presentation_mode = "iframe" if embed_probe.iframe_allowed else "external"
            checkout_row.status = "embedded_ready" if presentation_mode == "iframe" else "external_handoff"
            checkout_row.continue_url = cart.checkout_url
            checkout_row.fallback_url = cart.checkout_url
            checkout_row.payment_handlers_json = []
            checkout_row.shop_pay_supported = False
            checkout_row.requires_escalation = False
            checkout_row.presentation_mode = presentation_mode
            checkout_row.embedded_state_payload = {
                "store_domain": store_domain,
                "buyer_email": buyer_profile.email,
                "shipping_city": buyer_profile.shipping_address.city,
                "embed_preference": self.settings.shopify_checkout_embed_mode,
                "embed_probe": {
                    "final_url": embed_probe.final_url,
                    "status_code": embed_probe.status_code,
                    "iframe_allowed": embed_probe.iframe_allowed,
                    "block_reason": embed_probe.block_reason,
                    "x_frame_options": embed_probe.x_frame_options,
                    "frame_ancestors": embed_probe.frame_ancestors,
                    "allowed_embed_origins": embed_probe.allowed_embed_origins,
                    "error": embed_probe.error,
                },
            }
            checkout_row.order_total = cart.total_amount or cart.subtotal_amount
            checkout_row.currency = cart.currency
            checkout_row.error_code = None if embed_probe.iframe_allowed else "embedding_blocked"
            checkout_row.error_message = embed_probe.block_reason
            resolved_rows.append(checkout_row)

        await session.flush()
        for checkout_row in resolved_rows:
            await session.refresh(checkout_row)
        return [checkout_session_to_read(checkout_row) for checkout_row in resolved_rows]

    async def get_session(
        self,
        *,
        session: AsyncSession,
        run_id: str,
        store_domain: str,
    ) -> SupplementCheckoutSessionRead | None:
        checkout_row = await session.scalar(
            select(SupplementCheckoutSession).where(
                SupplementCheckoutSession.run_id == run_id,
                SupplementCheckoutSession.store_domain == store_domain,
            )
        )
        if checkout_row is None:
            return None
        return checkout_session_to_read(checkout_row)

    async def continue_session(
        self,
        *,
        session: AsyncSession,
        run_id: str,
        store_domain: str,
        payload: SupplementCheckoutContinueRequest,
    ) -> SupplementCheckoutSessionRead:
        checkout_row = await session.scalar(
            select(SupplementCheckoutSession).where(
                SupplementCheckoutSession.run_id == run_id,
                SupplementCheckoutSession.store_domain == store_domain,
            )
        )
        if checkout_row is None:
            raise LookupError("Checkout session not found.")

        if payload.action == "open_fallback":
            checkout_row.status = "external_handoff"
            checkout_row.presentation_mode = "external"
            checkout_row.error_code = None
            checkout_row.error_message = None
        else:
            checkout_row.status = "order_placed"
            checkout_row.error_code = None
            checkout_row.error_message = None
            checkout_row.order_confirmation_json = SupplementOrderConfirmation(
                confirmation_id=str(uuid4()),
                store_domain=checkout_row.store_domain,
                message=payload.message
                or "Order confirmed in the merchant checkout flow and synced back into Shopper.",
                order_total=payload.order_total or checkout_row.order_total,
                currency=payload.currency or checkout_row.currency,
                confirmation_url=payload.confirmation_url or checkout_row.continue_url,
            ).model_dump(mode="json")

        await session.flush()
        await session.refresh(checkout_row)
        return checkout_session_to_read(checkout_row)

    async def cancel_session(
        self,
        *,
        session: AsyncSession,
        run_id: str,
        store_domain: str,
        payload: SupplementCheckoutCancelRequest,
    ) -> SupplementCheckoutSessionRead:
        checkout_row = await session.scalar(
            select(SupplementCheckoutSession).where(
                SupplementCheckoutSession.run_id == run_id,
                SupplementCheckoutSession.store_domain == store_domain,
            )
        )
        if checkout_row is None:
            raise LookupError("Checkout session not found.")

        checkout_row.status = "cancelled"
        checkout_row.error_code = "cancelled"
        checkout_row.error_message = payload.reason or "User cancelled checkout."
        await session.flush()
        await session.refresh(checkout_row)
        return checkout_session_to_read(checkout_row)

    async def _probe_checkout_mode(self, cart: StoreCart) -> CheckoutEmbedProbeResult:
        if not cart.checkout_url:
            return CheckoutEmbedProbeResult(
                checkout_url="",
                final_url=None,
                status_code=None,
                iframe_allowed=False,
                block_reason="Checkout URL is missing.",
                x_frame_options=None,
                content_security_policy=None,
                frame_ancestors=[],
                allowed_embed_origins=[],
            )

        configured_mode = self.settings.shopify_checkout_embed_mode
        if configured_mode == "external":
            return CheckoutEmbedProbeResult(
                checkout_url=cart.checkout_url,
                final_url=cart.checkout_url,
                status_code=None,
                iframe_allowed=False,
                block_reason="Embedding disabled by SHOPIFY_CHECKOUT_EMBED_MODE=external.",
                x_frame_options=None,
                content_security_policy=None,
                frame_ancestors=[],
                allowed_embed_origins=[],
            )
        if configured_mode == "iframe":
            return CheckoutEmbedProbeResult(
                checkout_url=cart.checkout_url,
                final_url=cart.checkout_url,
                status_code=None,
                iframe_allowed=True,
                block_reason=None,
                x_frame_options=None,
                content_security_policy=None,
                frame_ancestors=[],
                allowed_embed_origins=[],
            )
        return await self.embed_probe_service.probe_checkout_url(cart.checkout_url)


def checkout_session_to_read(checkout_row: SupplementCheckoutSession) -> SupplementCheckoutSessionRead:
    order_confirmation = checkout_row.order_confirmation_json
    return SupplementCheckoutSessionRead(
        session_id=checkout_row.session_id,
        run_id=checkout_row.run_id,
        store_domain=checkout_row.store_domain,
        status=checkout_row.status,
        checkout_mcp_session_id=checkout_row.checkout_mcp_session_id,
        continue_url=checkout_row.continue_url,
        fallback_url=checkout_row.fallback_url,
        payment_handlers=checkout_row.payment_handlers_json or [],
        shop_pay_supported=checkout_row.shop_pay_supported,
        requires_escalation=checkout_row.requires_escalation,
        presentation_mode=checkout_row.presentation_mode,
        embedded_state_payload=checkout_row.embedded_state_payload or {},
        order_confirmation=(
            SupplementOrderConfirmation.model_validate(order_confirmation) if isinstance(order_confirmation, dict) else None
        ),
        order_total=checkout_row.order_total,
        currency=checkout_row.currency,
        error_code=checkout_row.error_code,
        error_message=checkout_row.error_message,
        created_at=checkout_row.created_at,
        updated_at=checkout_row.updated_at,
    )
