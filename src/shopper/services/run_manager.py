from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Awaitable, Callable, DefaultDict, Dict, List

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shopper.agents import invoke_planner_graph
from shopper.models import AuditLog, OrderItem, PlanRun, PurchaseOrder as PurchaseOrderRecord
from shopper.schemas import PlannerStateSnapshot, PurchaseOrder, RunEvent


class RunEventBus:
    def __init__(self) -> None:
        self._events: DefaultDict[str, List[RunEvent]] = defaultdict(list)
        self._conditions: DefaultDict[str, asyncio.Condition] = defaultdict(asyncio.Condition)

    async def publish(self, event: RunEvent) -> None:
        condition = self._conditions[event.run_id]
        async with condition:
            self._events[event.run_id].append(event)
            condition.notify_all()

    def list_events(self, run_id: str) -> List[RunEvent]:
        return list(self._events.get(run_id, []))

    async def wait_for_events(self, run_id: str, cursor: int, timeout: float = 1.0) -> List[RunEvent]:
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


class RunManager:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        graph,
        settings,
        event_bus: RunEventBus,
    ) -> None:
        self.session_factory = session_factory
        self.graph = graph
        self.settings = settings
        self.event_bus = event_bus
        self._tasks: Dict[str, asyncio.Task] = {}

    async def publish(self, event: RunEvent) -> None:
        await self.event_bus.publish(event)

    def start_run(self, run_id: str, initial_state: Dict[str, object]) -> None:
        if run_id in self._tasks and not self._tasks[run_id].done():
            return
        task = asyncio.create_task(self._execute_run(run_id=run_id, initial_state=initial_state))
        self._tasks[run_id] = task
        task.add_done_callback(lambda completed: self._tasks.pop(run_id, None))

    async def _execute_run(self, run_id: str, initial_state: Dict[str, object]) -> None:
        snapshot = PlannerStateSnapshot.model_validate(initial_state)
        try:
            result = await invoke_planner_graph(
                graph=self.graph,
                state=initial_state,
                settings=self.settings,
                source="api",
                event_emitter=self.publish,
            )
            await self._persist_result(run_id, result, status=result["status"])
        except Exception as exc:  # pragma: no cover - exercised through integration path
            failed_snapshot = snapshot.as_failed(str(exc))
            await self.publish(
                RunEvent(
                    event_id=run_id + "-error",
                    run_id=run_id,
                    event_type="error",
                    phase=snapshot.current_phase or "planning",
                    node_name="planner",
                    message=str(exc),
                    data={},
                )
            )
            await self._persist_result(run_id, failed_snapshot.model_dump(mode="json"), status="failed")

    async def _persist_result(self, run_id: str, state_snapshot: Dict[str, object], status: str) -> None:
        async with self.session_factory() as session:
            plan_run = await session.get(PlanRun, run_id)
            if plan_run is None:
                return
            plan_run.status = status
            plan_run.state_snapshot = jsonable_encoder(state_snapshot)
            await self._sync_orders(session, plan_run, PlannerStateSnapshot.model_validate(state_snapshot))
            await self._sync_audit_logs(session, run_id=plan_run.run_id, user_id=plan_run.user_id)
            await session.commit()

    async def persist_run_events(self, run_id: str) -> None:
        async with self.session_factory() as session:
            plan_run = await session.get(PlanRun, run_id)
            if plan_run is None:
                return
            await self._sync_audit_logs(session, run_id=run_id, user_id=plan_run.user_id)
            await session.commit()

    async def _sync_orders(
        self,
        session: AsyncSession,
        plan_run: PlanRun,
        snapshot: PlannerStateSnapshot,
    ) -> None:
        existing_order_ids = (
            await session.execute(
                select(PurchaseOrderRecord.order_id).where(PurchaseOrderRecord.run_id == plan_run.run_id)
            )
        ).scalars().all()
        if existing_order_ids:
            await session.execute(delete(OrderItem).where(OrderItem.order_id.in_(existing_order_ids)))
            await session.execute(delete(PurchaseOrderRecord).where(PurchaseOrderRecord.order_id.in_(existing_order_ids)))

        for order_payload in snapshot.purchase_orders:
            order = PurchaseOrder.model_validate(order_payload)
            session.add(
                PurchaseOrderRecord(
                    order_id=order.order_id,
                    run_id=plan_run.run_id,
                    user_id=plan_run.user_id,
                    store=order.store,
                    store_url=order.store_url,
                    channel=order.channel,
                    status=order.status,
                    subtotal=order.subtotal,
                    delivery_fee=order.delivery_fee,
                    total_cost=order.total_cost,
                    cart_url=order.cart_url,
                    checkout_url=order.checkout_url,
                    cart_screenshot_path=order.cart_screenshot_path,
                    failure_reason=order.failure_reason,
                    verification_json=order.verification.model_dump(mode="json") if order.verification else {},
                    confirmation_json=order.confirmation.model_dump(mode="json") if order.confirmation else {},
                )
            )
            for item in order.items:
                session.add(
                    OrderItem(
                        order_id=order.order_id,
                        requested_name=item.requested_name,
                        actual_name=item.actual_name,
                        requested_quantity=item.requested_quantity,
                        actual_quantity=item.actual_quantity,
                        unit=item.unit,
                        unit_price=item.unit_price,
                        line_total=item.line_total,
                        status=item.status,
                        notes=item.notes,
                        product_url=item.product_url,
                    )
                )

    async def _sync_audit_logs(self, session: AsyncSession, *, run_id: str, user_id: str) -> None:
        await session.execute(delete(AuditLog).where(AuditLog.run_id == run_id))
        for event in self.event_bus.list_events(run_id):
            session.add(
                AuditLog(
                    run_id=run_id,
                    user_id=user_id,
                    agent="planner",
                    action=event.event_type,
                    phase=event.phase,
                    node_name=event.node_name,
                    input_summary={"message": event.message},
                    output_summary=event.data,
                    screenshot_path=event.data.get("cart_screenshot_path")
                    if isinstance(event.data, dict)
                    else None,
                )
            )
