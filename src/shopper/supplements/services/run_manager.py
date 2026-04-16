from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import DefaultDict, Dict, List, Sequence
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shopper.agents.tools.browser_tools import BrowserCheckoutAgent
from shopper.config import Settings
from shopper.supplements.agents import invoke_supplement_graph
from shopper.supplements.models import SupplementBuyerProfile, SupplementCheckoutSession, SupplementRun
from shopper.supplements.schemas import (
    AgentCheckoutStartRequest,
    PaymentCredentials,
    ShippingAddress,
    StoreCart,
    StoreCartLine,
    SupplementCartUpdateRequest,
    SupplementBuyerProfileRead,
    SupplementBuyerProfileSnapshot,
    SupplementBuyerProfileUpsertRequest,
    SupplementCheckoutCancelRequest,
    SupplementCheckoutContinueRequest,
    SupplementCheckoutSessionRead,
    SupplementCheckoutStartRequest,
    SupplementOrderConfirmation,
    SupplementRunEvent,
    SupplementStateSnapshot,
)
from shopper.supplements.services.agent_checkout_orchestrator import AgentCheckoutOrchestrator
from shopper.supplements.services.embedded_checkout_orchestrator import (
    EmbeddedCheckoutOrchestrator,
    checkout_session_to_read,
)


class SupplementRunEventBus:
    def __init__(self) -> None:
        self._events: DefaultDict[str, List[SupplementRunEvent]] = defaultdict(list)
        self._conditions: DefaultDict[str, asyncio.Condition] = defaultdict(asyncio.Condition)

    async def publish(self, event: SupplementRunEvent) -> None:
        condition = self._conditions[event.run_id]
        async with condition:
            self._events[event.run_id].append(event)
            condition.notify_all()

    def list_events(self, run_id: str) -> List[SupplementRunEvent]:
        return list(self._events.get(run_id, []))

    async def wait_for_events(self, run_id: str, cursor: int, timeout: float = 1.0) -> List[SupplementRunEvent]:
        events = self.list_events(run_id)
        if len(events) > cursor:
            return events[cursor:]

        condition = self._conditions[run_id]
        try:
            async with condition:
                await asyncio.wait_for(condition.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return []
        return self.list_events(run_id)[cursor:]


class SupplementRunManager:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        graph,
        settings: Settings,
        event_bus: SupplementRunEventBus,
        embedded_checkout_orchestrator: EmbeddedCheckoutOrchestrator | None = None,
        checkout_agent: BrowserCheckoutAgent | None = None,
        agent_checkout_orchestrator: AgentCheckoutOrchestrator | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.graph = graph
        self.settings = settings
        self.event_bus = event_bus
        self.checkout_agent = checkout_agent or BrowserCheckoutAgent(settings)
        self.embedded_checkout_orchestrator = embedded_checkout_orchestrator or EmbeddedCheckoutOrchestrator(settings)
        self.agent_checkout_orchestrator = agent_checkout_orchestrator or AgentCheckoutOrchestrator(
            settings,
            checkout_backend=self.checkout_agent.automation_backend,
            artifact_root=self.checkout_agent.artifact_root,
        )
        self._tasks: Dict[str, asyncio.Task] = {}
        self._checkout_tasks: Dict[str, asyncio.Task] = {}

    async def publish(self, event: SupplementRunEvent) -> None:
        await self.event_bus.publish(event)

    def start_run(self, run_id: str, initial_state: Dict[str, object]) -> None:
        if run_id in self._tasks and not self._tasks[run_id].done():
            return

        task = asyncio.create_task(self._execute_run(run_id=run_id, initial_state=initial_state))
        self._tasks[run_id] = task
        task.add_done_callback(lambda completed: self._tasks.pop(run_id, None))

    async def approve_run(self, run_id: str, approved_store_domains: Sequence[str] | None = None) -> SupplementRun:
        return await self.approve_stores(run_id, approved_store_domains=approved_store_domains)

    async def approve_stores(self, run_id: str, approved_store_domains: Sequence[str] | None = None) -> SupplementRun:
        async with self.session_factory() as session:
            supplement_run = await session.get(SupplementRun, run_id)
            if supplement_run is None:
                raise LookupError("Run not found.")

            snapshot = SupplementStateSnapshot.model_validate(supplement_run.state_snapshot)
            if snapshot.status == "completed" and snapshot.current_phase == "checkout":
                return supplement_run
            if snapshot.current_phase != "checkout" or snapshot.status not in {"awaiting_approval", "running"}:
                raise ValueError("Run is not waiting for supplement approval.")

            ready_domains = [cart.store_domain.lower() for cart in snapshot.store_carts if cart.checkout_url]
            if not ready_domains:
                raise RuntimeError("Supplement run does not have any checkout-ready carts.")

            requested_domains = [domain.lower() for domain in approved_store_domains or []]
            if requested_domains:
                invalid_domains = sorted(set(requested_domains) - set(ready_domains))
                if invalid_domains:
                    raise ValueError(
                        "Approved stores must be one of: {stores}".format(stores=", ".join(sorted(set(ready_domains))))
                    )
                resolved_domains = [domain for domain in ready_domains if domain in set(requested_domains)]
            else:
                resolved_domains = ready_domains

            if not resolved_domains:
                raise ValueError("At least one checkout-ready store must be approved.")

            buyer_profile = await _load_buyer_profile(session, supplement_run.user_id)
            updated_snapshot = _synchronize_snapshot(
                snapshot,
                buyer_profile=buyer_profile,
                checkout_sessions=await _list_checkout_sessions(session, run_id),
            ).model_copy(
                update={
                    "approved_store_domains": resolved_domains,
                    "status": "running",
                    "current_node": "buyer_profile_gate" if not buyer_profile or not buyer_profile.is_ready else "approval_gate",
                    "current_phase": "checkout",
                    "latest_error": None,
                    "fallback_reason": None,
                }
            )
            supplement_run.status = updated_snapshot.status
            supplement_run.state_snapshot = _encode_snapshot(updated_snapshot.model_dump(mode="json"))
            await session.commit()
            await session.refresh(supplement_run)

        await self.publish(
            SupplementRunEvent(
                event_id=str(uuid4()),
                run_id=run_id,
                event_type="approval_resolved",
                phase="checkout",
                node_name="approval_gate",
                message="Approved checkout links for {count} store(s).".format(count=len(resolved_domains)),
                data={
                    "approved_store_domains": resolved_domains,
                },
            )
        )
        return supplement_run

    async def get_buyer_profile(self, run_id: str) -> SupplementBuyerProfileRead | None:
        async with self.session_factory() as session:
            supplement_run = await session.get(SupplementRun, run_id)
            if supplement_run is None:
                raise LookupError("Run not found.")
            return await _load_buyer_profile(session, supplement_run.user_id)

    async def update_cart_quantities(
        self,
        run_id: str,
        payload: SupplementCartUpdateRequest,
    ) -> SupplementRun:
        async with self.session_factory() as session:
            supplement_run = await session.get(SupplementRun, run_id)
            if supplement_run is None:
                raise LookupError("Run not found.")

            snapshot = SupplementStateSnapshot.model_validate(supplement_run.state_snapshot)
            if snapshot.current_phase != "checkout":
                raise ValueError("Cart quantities can only be edited after carts are ready.")

            checkout_sessions = await _list_checkout_sessions(session, run_id)
            if any(not checkout_session.is_terminal for checkout_session in checkout_sessions):
                raise ValueError("Cart quantities cannot be edited while checkout is running.")
            if any(checkout_session.status == "order_placed" for checkout_session in checkout_sessions):
                raise ValueError("Cart quantities cannot be edited after an order has been placed.")

            updated_carts = _apply_cart_quantity_updates(snapshot.store_carts, payload)
            updated_stack = _apply_stack_quantity_updates(snapshot, payload)
            buyer_profile = await _load_buyer_profile(session, supplement_run.user_id)
            updated_snapshot = _synchronize_snapshot(
                snapshot.model_copy(
                    update={
                        "store_carts": updated_carts,
                        "recommended_stack": updated_stack,
                        "latest_error": None,
                    }
                ),
                buyer_profile=buyer_profile,
                checkout_sessions=checkout_sessions,
            )
            supplement_run.state_snapshot = _encode_snapshot(updated_snapshot.model_dump(mode="json"))
            await session.commit()
            await session.refresh(supplement_run)

        await self.publish(
            SupplementRunEvent(
                event_id=str(uuid4()),
                run_id=run_id,
                event_type="node_completed",
                phase="checkout",
                node_name="cart_quantity_editor",
                message="Updated checkout cart quantities.",
                data={"status": "cart_updated"},
            )
        )
        return supplement_run

    async def upsert_buyer_profile(
        self,
        run_id: str,
        payload: SupplementBuyerProfileUpsertRequest,
    ) -> SupplementBuyerProfileRead:
        async with self.session_factory() as session:
            supplement_run = await session.get(SupplementRun, run_id)
            if supplement_run is None:
                raise LookupError("Run not found.")

            buyer_profile_row = await session.get(SupplementBuyerProfile, supplement_run.user_id)
            if buyer_profile_row is None:
                buyer_profile_row = SupplementBuyerProfile(user_id=supplement_run.user_id)
                session.add(buyer_profile_row)

            buyer_profile_row.email = payload.email
            buyer_profile_row.shipping_name = payload.shipping_name
            buyer_profile_row.shipping_address_json = payload.shipping_address.model_dump(mode="json")
            buyer_profile_row.billing_same_as_shipping = payload.billing_same_as_shipping
            buyer_profile_row.billing_country = payload.billing_country
            buyer_profile_row.consent_granted = payload.consent_granted
            buyer_profile_row.autopurchase_enabled = payload.autopurchase_enabled
            buyer_profile_row.max_order_total = payload.max_order_total
            buyer_profile_row.max_monthly_total = payload.max_monthly_total
            buyer_profile_row.shop_pay_linked = payload.shop_pay_linked
            buyer_profile_row.shop_pay_last_verified_at = payload.shop_pay_last_verified_at
            buyer_profile_row.last_payment_authorization_at = payload.last_payment_authorization_at
            buyer_profile_row.consent_version = payload.consent_version

            await session.flush()
            await session.refresh(buyer_profile_row)

            buyer_profile = _buyer_profile_to_read(buyer_profile_row)
            snapshot = SupplementStateSnapshot.model_validate(supplement_run.state_snapshot)
            updated_snapshot = _synchronize_snapshot(
                snapshot,
                buyer_profile=buyer_profile,
                checkout_sessions=await _list_checkout_sessions(session, run_id),
            ).model_copy(
                update={
                    "current_phase": snapshot.current_phase or "checkout",
                    "current_node": "buyer_profile_ready",
                }
            )
            supplement_run.state_snapshot = _encode_snapshot(updated_snapshot.model_dump(mode="json"))
            await session.commit()
            return buyer_profile

    async def start_checkout(
        self,
        run_id: str,
        payload: SupplementCheckoutStartRequest | None = None,
    ) -> SupplementRun:
        async with self.session_factory() as session:
            supplement_run = await session.get(SupplementRun, run_id)
            if supplement_run is None:
                raise LookupError("Run not found.")

            snapshot = SupplementStateSnapshot.model_validate(supplement_run.state_snapshot)
            if snapshot.current_phase != "checkout":
                raise ValueError("Run is not ready for supplement checkout.")

            buyer_profile = await _load_buyer_profile(session, supplement_run.user_id)
            if buyer_profile is None or not buyer_profile.is_ready:
                raise ValueError("Buyer profile is incomplete. Save shipping and consent details before checkout.")

            requested_domains = [domain.lower() for domain in (payload.store_domains if payload else [])]
            approved_store_domains = snapshot.approved_store_domains or requested_domains
            if not approved_store_domains:
                raise ValueError("Approve at least one store before starting checkout.")

            if requested_domains:
                invalid_domains = sorted(set(requested_domains) - set(snapshot.approved_store_domains))
                if invalid_domains:
                    raise ValueError(
                        "Checkout can only start for approved stores: {stores}".format(
                            stores=", ".join(sorted(set(snapshot.approved_store_domains)))
                        )
                    )
                approved_store_domains = requested_domains

            checkout_sessions = await self.embedded_checkout_orchestrator.prepare_sessions(
                session=session,
                run_id=run_id,
                store_carts=snapshot.store_carts,
                approved_store_domains=approved_store_domains,
                buyer_profile=buyer_profile,
            )
            updated_snapshot = _synchronize_snapshot(
                snapshot,
                buyer_profile=buyer_profile,
                checkout_sessions=checkout_sessions,
            ).model_copy(
                update={
                    "approved_store_domains": approved_store_domains,
                    "status": "running",
                    "current_phase": "checkout",
                    "current_node": "embedded_checkout_orchestrator",
                    "latest_error": None,
                }
            )

            supplement_run.status = updated_snapshot.status
            supplement_run.state_snapshot = _encode_snapshot(updated_snapshot.model_dump(mode="json"))
            await session.commit()
            await session.refresh(supplement_run)
            return supplement_run

    async def start_agent_checkout(
        self,
        run_id: str,
        payload: AgentCheckoutStartRequest,
    ) -> SupplementRun:
        existing_task = self._checkout_tasks.get(run_id)
        if existing_task is not None and not existing_task.done():
            raise ValueError("Agent checkout is already running for this supplement run.")

        async with self.session_factory() as session:
            supplement_run = await session.get(SupplementRun, run_id)
            if supplement_run is None:
                raise LookupError("Run not found.")

            snapshot = SupplementStateSnapshot.model_validate(supplement_run.state_snapshot)
            if snapshot.current_phase != "checkout":
                raise ValueError("Run is not ready for supplement checkout.")

            buyer_profile = await _load_buyer_profile(session, supplement_run.user_id)
            if buyer_profile is None or not buyer_profile.is_ready:
                raise ValueError("Buyer profile is incomplete. Save shipping and consent details before checkout.")

            ready_domains = [cart.store_domain.lower() for cart in snapshot.store_carts if cart.checkout_url]
            if not ready_domains:
                raise RuntimeError("Supplement run does not have any checkout-ready carts.")

            requested_domains = [domain.lower() for domain in payload.store_domains]
            if requested_domains:
                invalid_domains = sorted(set(requested_domains) - set(ready_domains))
                if invalid_domains:
                    raise ValueError(
                        "Agent checkout can only start for checkout-ready stores: {stores}".format(
                            stores=", ".join(sorted(set(ready_domains)))
                        )
                    )

            approved_store_domains = snapshot.approved_store_domains or requested_domains
            if requested_domains and snapshot.approved_store_domains:
                invalid_domains = sorted(set(requested_domains) - set(snapshot.approved_store_domains))
                if invalid_domains:
                    raise ValueError(
                        "Agent checkout can only start for approved stores: {stores}".format(
                            stores=", ".join(sorted(set(snapshot.approved_store_domains)))
                        )
                    )
                approved_store_domains = requested_domains
            elif requested_domains:
                approved_store_domains = requested_domains
            else:
                approved_store_domains = [domain for domain in snapshot.approved_store_domains if domain in set(ready_domains)]

            if not approved_store_domains:
                raise ValueError("Approve at least one store before starting checkout.")

            existing_rows = await session.scalars(
                select(SupplementCheckoutSession).where(SupplementCheckoutSession.run_id == run_id)
            )
            existing_by_domain = {row.store_domain.lower(): row for row in existing_rows}
            cart_by_domain = {cart.store_domain.lower(): cart for cart in snapshot.store_carts if cart.checkout_url}

            for store_domain in approved_store_domains:
                cart = cart_by_domain.get(store_domain)
                if cart is None or not cart.checkout_url:
                    continue

                checkout_row = existing_by_domain.get(store_domain)
                if checkout_row is None:
                    checkout_row = SupplementCheckoutSession(
                        session_id=str(uuid4()),
                        run_id=run_id,
                        store_domain=store_domain,
                    )
                    session.add(checkout_row)

                checkout_row.status = "agent_running"
                checkout_row.continue_url = cart.checkout_url
                checkout_row.fallback_url = cart.checkout_url
                checkout_row.payment_handlers_json = []
                checkout_row.shop_pay_supported = False
                checkout_row.requires_escalation = False
                checkout_row.presentation_mode = "agent"
                checkout_row.embedded_state_payload = {
                    "store_domain": store_domain,
                    "buyer_email": buyer_profile.email,
                    "agent_status_text": (
                        "Waiting for cloud browser stream..."
                        if self.settings.browser_checkout_use_cloud
                        else "Waiting for browser agent window..."
                    ),
                    "agent_step": "queued",
                    "agent_view_mode": "cloud" if self.settings.browser_checkout_use_cloud else "local",
                }
                checkout_row.order_confirmation_json = None
                checkout_row.order_total = cart.total_amount or cart.subtotal_amount
                checkout_row.currency = cart.currency
                checkout_row.error_code = None
                checkout_row.error_message = None

            await session.flush()
            checkout_sessions = await _list_checkout_sessions(session, run_id)
            updated_snapshot = _synchronize_snapshot(
                snapshot,
                buyer_profile=buyer_profile,
                checkout_sessions=checkout_sessions,
            ).model_copy(
                update={
                    "approved_store_domains": approved_store_domains,
                    "status": "running",
                    "current_phase": "checkout",
                    "current_node": "agent_checkout_orchestrator",
                    "active_checkout_store": approved_store_domains[0] if approved_store_domains else None,
                    "latest_error": None,
                    "fallback_reason": None,
                }
            )

            supplement_run.status = updated_snapshot.status
            supplement_run.state_snapshot = _encode_snapshot(updated_snapshot.model_dump(mode="json"))
            await session.commit()
            await session.refresh(supplement_run)

        task = asyncio.create_task(
            self._execute_agent_checkout(
                run_id=run_id,
                store_carts=snapshot.store_carts,
                approved_store_domains=approved_store_domains,
                buyer_profile=buyer_profile,
                payment_credentials=payload.payment_credentials,
                simulate_success=payload.simulate_success,
            )
        )
        self._checkout_tasks[run_id] = task
        task.add_done_callback(lambda completed: self._checkout_tasks.pop(run_id, None))
        return supplement_run

    async def get_checkout_session(self, run_id: str, store_domain: str) -> SupplementCheckoutSessionRead:
        async with self.session_factory() as session:
            supplement_run = await session.get(SupplementRun, run_id)
            if supplement_run is None:
                raise LookupError("Run not found.")

            checkout_session = await self.embedded_checkout_orchestrator.get_session(
                session=session,
                run_id=run_id,
                store_domain=store_domain.lower(),
            )
            if checkout_session is None:
                raise LookupError("Checkout session not found.")
            return checkout_session

    async def continue_checkout(
        self,
        run_id: str,
        store_domain: str,
        payload: SupplementCheckoutContinueRequest,
    ) -> SupplementRun:
        return await self._update_checkout_session(
            run_id=run_id,
            store_domain=store_domain.lower(),
            action="continue",
            continue_payload=payload,
        )

    async def cancel_checkout(
        self,
        run_id: str,
        store_domain: str,
        payload: SupplementCheckoutCancelRequest,
    ) -> SupplementRun:
        return await self._update_checkout_session(
            run_id=run_id,
            store_domain=store_domain.lower(),
            action="cancel",
            cancel_payload=payload,
        )

    async def _update_checkout_session(
        self,
        *,
        run_id: str,
        store_domain: str,
        action: str,
        continue_payload: SupplementCheckoutContinueRequest | None = None,
        cancel_payload: SupplementCheckoutCancelRequest | None = None,
    ) -> SupplementRun:
        async with self.session_factory() as session:
            supplement_run = await session.get(SupplementRun, run_id)
            if supplement_run is None:
                raise LookupError("Run not found.")

            snapshot = SupplementStateSnapshot.model_validate(supplement_run.state_snapshot)
            if action == "cancel":
                assert cancel_payload is not None
                await self.embedded_checkout_orchestrator.cancel_session(
                    session=session,
                    run_id=run_id,
                    store_domain=store_domain,
                    payload=cancel_payload,
                )
            else:
                assert continue_payload is not None
                await self.embedded_checkout_orchestrator.continue_session(
                    session=session,
                    run_id=run_id,
                    store_domain=store_domain,
                    payload=continue_payload,
                )

            buyer_profile = await _load_buyer_profile(session, supplement_run.user_id)
            checkout_sessions = await _list_checkout_sessions(session, run_id)
            run_status = _derive_checkout_run_status(checkout_sessions)
            current_node = _derive_checkout_node(run_status, checkout_sessions)
            fallback_reason = snapshot.fallback_reason
            if continue_payload and continue_payload.action == "open_fallback":
                fallback_reason = "Embedding was unavailable, so checkout moved to a controlled external handoff."

            updated_snapshot = _synchronize_snapshot(
                snapshot,
                buyer_profile=buyer_profile,
                checkout_sessions=checkout_sessions,
            ).model_copy(
                update={
                    "status": run_status,
                    "current_phase": "checkout",
                    "current_node": current_node,
                    "latest_error": _latest_checkout_error(checkout_sessions),
                    "fallback_reason": fallback_reason,
                }
            )
            supplement_run.status = updated_snapshot.status
            supplement_run.state_snapshot = _encode_snapshot(updated_snapshot.model_dump(mode="json"))
            await session.commit()
            await session.refresh(supplement_run)

        if run_status in {"completed", "failed"}:
            await self.publish(
                SupplementRunEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    event_type="run_completed",
                    phase="checkout",
                    node_name=current_node,
                    message=_completion_message(run_status, checkout_sessions),
                    data={
                        "status": run_status,
                        "approved_store_domains": supplement_run.state_snapshot.get("approved_store_domains", []),
                    },
                )
            )

        return supplement_run

    async def _execute_agent_checkout(
        self,
        *,
        run_id: str,
        store_carts,
        approved_store_domains: list[str],
        buyer_profile: SupplementBuyerProfileRead,
        payment_credentials: PaymentCredentials,
        simulate_success: bool = False,
    ) -> None:
        try:
            await self.agent_checkout_orchestrator.execute_agent_checkout(
                session_factory=self.session_factory,
                run_id=run_id,
                store_carts=store_carts,
                approved_store_domains=approved_store_domains,
                buyer_profile=buyer_profile,
                payment_credentials=payment_credentials,
                simulate_success=simulate_success,
                event_emitter=self.publish,
                settings=self.settings,
            )

            async with self.session_factory() as session:
                supplement_run = await session.get(SupplementRun, run_id)
                if supplement_run is None:
                    return

                snapshot = SupplementStateSnapshot.model_validate(supplement_run.state_snapshot)
                refreshed_buyer_profile = await _load_buyer_profile(session, supplement_run.user_id)
                checkout_sessions = await _list_checkout_sessions(session, run_id)
                run_status = _derive_checkout_run_status(checkout_sessions)
                current_node = _derive_checkout_node(run_status, checkout_sessions)

                updated_snapshot = _synchronize_snapshot(
                    snapshot,
                    buyer_profile=refreshed_buyer_profile,
                    checkout_sessions=checkout_sessions,
                ).model_copy(
                    update={
                        "status": run_status,
                        "current_phase": "checkout",
                        "current_node": current_node,
                        "latest_error": _latest_checkout_error(checkout_sessions),
                        "fallback_reason": None,
                    }
                )
                supplement_run.status = updated_snapshot.status
                supplement_run.state_snapshot = _encode_snapshot(updated_snapshot.model_dump(mode="json"))
                await session.commit()

            await self.publish(
                SupplementRunEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    event_type="run_completed",
                    phase="checkout",
                    node_name=current_node,
                    message=_completion_message(run_status, checkout_sessions),
                    data={
                        "status": run_status,
                        "approved_store_domains": approved_store_domains,
                    },
                )
            )
        except Exception as exc:  # pragma: no cover - catastrophic background task failures are integration-tested
            async with self.session_factory() as session:
                supplement_run = await session.get(SupplementRun, run_id)
                if supplement_run is not None:
                    snapshot = SupplementStateSnapshot.model_validate(supplement_run.state_snapshot)
                    refreshed_buyer_profile = await _load_buyer_profile(session, supplement_run.user_id)
                    checkout_sessions = await _list_checkout_sessions(session, run_id)
                    failed_snapshot = _synchronize_snapshot(
                        snapshot,
                        buyer_profile=refreshed_buyer_profile,
                        checkout_sessions=checkout_sessions,
                    ).model_copy(
                        update={
                            "status": "failed",
                            "current_phase": "checkout",
                            "current_node": "agent_checkout_orchestrator",
                            "latest_error": str(exc),
                        }
                    )
                    supplement_run.status = "failed"
                    supplement_run.state_snapshot = _encode_snapshot(failed_snapshot.model_dump(mode="json"))
                    await session.commit()

            await self.publish(
                SupplementRunEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    event_type="error",
                    phase="checkout",
                    node_name="agent_checkout_orchestrator",
                    message=str(exc),
                    data={},
                )
            )

    async def _execute_run(self, run_id: str, initial_state: Dict[str, object]) -> None:
        snapshot = SupplementStateSnapshot.model_validate(initial_state)
        try:
            result = await invoke_supplement_graph(
                graph=self.graph,
                state=initial_state,
                settings=self.settings,
                source="api",
                event_emitter=self.publish,
            )
            await self._persist_result(run_id, result, status=str(result["status"]))
        except Exception as exc:  # pragma: no cover - exercised through integration path
            failed_snapshot = snapshot.as_failed(str(exc))
            await self.publish(
                SupplementRunEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    event_type="error",
                    phase=snapshot.current_phase or "memory",
                    node_name=snapshot.current_node or "supplement_graph",
                    message=str(exc),
                    data={},
                )
            )
            await self._persist_result(run_id, failed_snapshot.model_dump(mode="json"), status="failed")

    async def _persist_result(self, run_id: str, state_snapshot: Dict[str, object], status: str) -> None:
        async with self.session_factory() as session:
            supplement_run = await session.get(SupplementRun, run_id)
            if supplement_run is None:
                return

            snapshot = SupplementStateSnapshot.model_validate(state_snapshot)
            buyer_profile = await _load_buyer_profile(session, snapshot.user_id)
            checkout_sessions = await _list_checkout_sessions(session, run_id)
            merged_snapshot = _synchronize_snapshot(
                snapshot,
                buyer_profile=buyer_profile,
                checkout_sessions=checkout_sessions,
            ).model_copy(update={"status": status})
            supplement_run.status = status
            supplement_run.state_snapshot = _encode_snapshot(merged_snapshot.model_dump(mode="json"))
            await session.commit()


def _encode_snapshot(state_snapshot: Dict[str, object]) -> dict:
    snapshot = SupplementStateSnapshot.model_validate(state_snapshot)
    encoded = jsonable_encoder(snapshot.model_dump(mode="json"))
    trace_metadata = state_snapshot.get("trace_metadata")
    if isinstance(trace_metadata, dict):
        encoded["trace_metadata"] = trace_metadata
    return encoded


async def _load_buyer_profile(session: AsyncSession, user_id: str) -> SupplementBuyerProfileRead | None:
    buyer_profile_row = await session.get(SupplementBuyerProfile, user_id)
    if buyer_profile_row is None:
        return None
    return _buyer_profile_to_read(buyer_profile_row)


def _buyer_profile_to_read(buyer_profile_row: SupplementBuyerProfile) -> SupplementBuyerProfileRead:
    shipping_address_json = buyer_profile_row.shipping_address_json if isinstance(buyer_profile_row.shipping_address_json, dict) else {}
    return SupplementBuyerProfileRead(
        user_id=buyer_profile_row.user_id,
        email=buyer_profile_row.email,
        shipping_name=buyer_profile_row.shipping_name,
        shipping_address=ShippingAddress.model_validate(shipping_address_json),
        billing_same_as_shipping=buyer_profile_row.billing_same_as_shipping,
        billing_country=buyer_profile_row.billing_country,
        consent_granted=buyer_profile_row.consent_granted,
        autopurchase_enabled=buyer_profile_row.autopurchase_enabled,
        max_order_total=buyer_profile_row.max_order_total,
        max_monthly_total=buyer_profile_row.max_monthly_total,
        shop_pay_linked=buyer_profile_row.shop_pay_linked,
        shop_pay_last_verified_at=buyer_profile_row.shop_pay_last_verified_at,
        last_payment_authorization_at=buyer_profile_row.last_payment_authorization_at,
        consent_version=buyer_profile_row.consent_version,
        created_at=buyer_profile_row.created_at,
        updated_at=buyer_profile_row.updated_at,
    )


async def _list_checkout_sessions(session: AsyncSession, run_id: str) -> list[SupplementCheckoutSessionRead]:
    rows = await session.scalars(
        select(SupplementCheckoutSession)
        .where(SupplementCheckoutSession.run_id == run_id)
        .order_by(SupplementCheckoutSession.store_domain.asc())
    )
    return [checkout_session_to_read(row) for row in rows]


def _apply_cart_quantity_updates(
    store_carts: list[StoreCart],
    payload: SupplementCartUpdateRequest,
) -> list[StoreCart]:
    unmatched_update_indexes = set(range(len(payload.updates)))
    updated_carts: list[StoreCart] = []

    for cart in store_carts:
        store_updates = [
            (index, update)
            for index, update in enumerate(payload.updates)
            if update.store_domain.lower() == cart.store_domain.lower()
        ]
        if not store_updates:
            updated_carts.append(cart)
            continue

        next_lines: list[StoreCartLine] = []
        changed = False
        for line in cart.lines:
            matched_update = next(
                (
                    (index, update)
                    for index, update in reversed(store_updates)
                    if _cart_update_matches_line(update, line)
                ),
                None,
            )
            if matched_update is None:
                next_lines.append(line)
                continue

            update_index, update = matched_update
            unmatched_update_indexes.discard(update_index)
            changed = True
            next_lines.append(_cart_line_with_quantity(line, update.quantity))

        if not changed:
            updated_carts.append(cart)
            continue

        subtotal_amount = _sum_optional_amounts(line.subtotal_amount for line in next_lines)
        total_amount = _sum_optional_amounts(line.total_amount for line in next_lines)
        instructions = cart.instructions or ""
        update_note = "Quantities were edited in Shopper; verify the merchant cart matches before checkout."
        if update_note not in instructions:
            instructions = " ".join([instructions, update_note]).strip()

        updated_carts.append(
            cart.model_copy(
                update={
                    "lines": next_lines,
                    "total_quantity": sum(line.quantity for line in next_lines),
                    "subtotal_amount": subtotal_amount if subtotal_amount is not None else cart.subtotal_amount,
                    "total_amount": total_amount if total_amount is not None else cart.total_amount,
                    "instructions": instructions,
                }
            )
        )

    if unmatched_update_indexes:
        missing = ", ".join(
            sorted(
                {
                    payload.updates[index].store_domain
                    for index in unmatched_update_indexes
                }
            )
        )
        raise ValueError(f"Could not find cart line(s) to update for: {missing}.")

    return updated_carts


def _apply_stack_quantity_updates(
    snapshot: SupplementStateSnapshot,
    payload: SupplementCartUpdateRequest,
):
    if snapshot.recommended_stack is None:
        return None

    next_items = []
    changed = False
    for item in snapshot.recommended_stack.items:
        matched_update = next(
            (
                update
                for update in reversed(payload.updates)
                if _cart_update_matches_stack_item(snapshot.store_carts, update, item)
            ),
            None,
        )
        if matched_update is None:
            next_items.append(item)
            continue

        changed = True
        unit_monthly_cost = (
            item.monthly_cost / max(item.quantity, 1)
            if item.monthly_cost is not None
            else None
        )
        next_items.append(
            item.model_copy(
                update={
                    "quantity": matched_update.quantity,
                    "monthly_cost": (
                        round(unit_monthly_cost * matched_update.quantity, 2)
                        if unit_monthly_cost is not None
                        else item.monthly_cost
                    ),
                }
            )
        )

    if not changed:
        return snapshot.recommended_stack

    total_monthly_cost = _sum_optional_amounts(item.monthly_cost for item in next_items)
    return snapshot.recommended_stack.model_copy(
        update={
            "items": next_items,
            "total_monthly_cost": total_monthly_cost,
        }
    )


def _cart_update_matches_stack_item(store_carts: list[StoreCart], update, item) -> bool:
    if update.store_domain.lower() != item.product.store_domain.lower():
        return False

    resolved_product_id = update.product_id
    resolved_variant_id = update.variant_id
    if not resolved_product_id and not resolved_variant_id:
        line = _find_cart_line_for_update(store_carts, update)
        if line is not None:
            resolved_product_id = line.product_id
            resolved_variant_id = line.variant_id

    if resolved_product_id and resolved_product_id == item.product.product_id:
        return True
    if (
        resolved_variant_id
        and item.product.default_variant is not None
        and resolved_variant_id == item.product.default_variant.variant_id
    ):
        return True
    return False


def _find_cart_line_for_update(store_carts: list[StoreCart], update) -> StoreCartLine | None:
    for cart in store_carts:
        if update.store_domain.lower() != cart.store_domain.lower():
            continue
        for line in cart.lines:
            if _cart_update_matches_line(update, line):
                return line
    return None


def _cart_update_matches_line(update, line: StoreCartLine) -> bool:
    if update.line_id and line.line_id and update.line_id == line.line_id:
        return True
    if update.variant_id and update.variant_id == line.variant_id:
        return True
    if update.product_id and update.product_id == line.product_id:
        return True
    return False


def _cart_line_with_quantity(line: StoreCartLine, quantity: int) -> StoreCartLine:
    old_quantity = max(line.quantity, 1)
    unit_subtotal = line.subtotal_amount / old_quantity if line.subtotal_amount is not None else None
    unit_total = line.total_amount / old_quantity if line.total_amount is not None else None
    return line.model_copy(
        update={
            "quantity": quantity,
            "subtotal_amount": round(unit_subtotal * quantity, 2) if unit_subtotal is not None else None,
            "total_amount": round(unit_total * quantity, 2) if unit_total is not None else None,
        }
    )


def _sum_optional_amounts(values) -> float | None:
    total = 0.0
    saw_value = False
    for value in values:
        if value is None:
            return None
        saw_value = True
        total += value
    return round(total, 2) if saw_value else None


def _synchronize_snapshot(
    snapshot: SupplementStateSnapshot,
    *,
    buyer_profile: SupplementBuyerProfileRead | None,
    checkout_sessions: list[SupplementCheckoutSessionRead],
) -> SupplementStateSnapshot:
    active_session = next((session for session in checkout_sessions if not session.is_terminal), None)
    payment_handlers = active_session.payment_handlers if active_session else []
    continue_url = active_session.continue_url if active_session else None
    fallback_reason = snapshot.fallback_reason
    if not fallback_reason:
        external_session = next((session for session in checkout_sessions if session.status == "external_handoff"), None)
        if external_session is not None:
            fallback_reason = "Checkout is using a controlled merchant handoff because embedding is not available."

    return snapshot.model_copy(
        update={
            "buyer_profile": SupplementBuyerProfileSnapshot.from_profile(buyer_profile) if buyer_profile else None,
            "buyer_profile_ready": buyer_profile.is_ready if buyer_profile else False,
            "checkout_sessions": checkout_sessions,
            "active_checkout_store": active_session.store_domain if active_session else None,
            "continue_url": continue_url,
            "payment_handlers": payment_handlers,
            "order_confirmations": [session.order_confirmation for session in checkout_sessions if session.order_confirmation],
            "fallback_reason": fallback_reason,
        }
    )


def _derive_checkout_run_status(checkout_sessions: list[SupplementCheckoutSessionRead]) -> str:
    if not checkout_sessions:
        return "running"
    if any(not session.is_terminal for session in checkout_sessions):
        return "running"
    if any(session.status == "failed" for session in checkout_sessions):
        placed_orders = any(session.status == "order_placed" for session in checkout_sessions)
        return "completed" if placed_orders else "failed"
    return "completed"


def _derive_checkout_node(run_status: str, checkout_sessions: list[SupplementCheckoutSessionRead]) -> str:
    if run_status == "completed":
        return "order_confirmation"
    if run_status == "failed":
        return "checkout_attention_required"
    if any(session.presentation_mode == "agent" for session in checkout_sessions):
        return "agent_checkout_orchestrator"
    if any(session.status == "external_handoff" for session in checkout_sessions):
        return "checkout_handoff"
    return "embedded_checkout_orchestrator"


def _latest_checkout_error(checkout_sessions: list[SupplementCheckoutSessionRead]) -> str | None:
    for checkout_session in checkout_sessions:
        if checkout_session.error_message:
            return checkout_session.error_message
    return None


def _completion_message(run_status: str, checkout_sessions: list[SupplementCheckoutSessionRead]) -> str:
    if run_status == "failed":
        return "Checkout ended with merchant issues and needs attention."

    confirmations: list[SupplementOrderConfirmation] = [
        session.order_confirmation for session in checkout_sessions if session.order_confirmation
    ]
    if confirmations:
        return "Placed {count} supplement order(s) and synced the confirmations into the conversation.".format(
            count=len(confirmations)
        )
    return "Checkout was wrapped up without placing an order."
