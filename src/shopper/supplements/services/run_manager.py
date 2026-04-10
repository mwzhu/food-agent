from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import DefaultDict, Dict, List, Sequence
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shopper.config import Settings
from shopper.supplements.agents import invoke_supplement_graph
from shopper.supplements.models import SupplementRun
from shopper.supplements.schemas import SupplementRunEvent, SupplementStateSnapshot


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
    ) -> None:
        self.session_factory = session_factory
        self.graph = graph
        self.settings = settings
        self.event_bus = event_bus
        self._tasks: Dict[str, asyncio.Task] = {}

    async def publish(self, event: SupplementRunEvent) -> None:
        await self.event_bus.publish(event)

    def start_run(self, run_id: str, initial_state: Dict[str, object]) -> None:
        if run_id in self._tasks and not self._tasks[run_id].done():
            return

        task = asyncio.create_task(self._execute_run(run_id=run_id, initial_state=initial_state))
        self._tasks[run_id] = task
        task.add_done_callback(lambda completed: self._tasks.pop(run_id, None))

    async def approve_run(self, run_id: str, approved_store_domains: Sequence[str] | None = None) -> SupplementRun:
        async with self.session_factory() as session:
            supplement_run = await session.get(SupplementRun, run_id)
            if supplement_run is None:
                raise LookupError("Run not found.")

            snapshot = SupplementStateSnapshot.model_validate(supplement_run.state_snapshot)
            if snapshot.status == "completed" and snapshot.current_phase == "checkout":
                return supplement_run
            if snapshot.status != "awaiting_approval" or snapshot.current_phase != "checkout":
                raise ValueError("Run is not waiting for supplement approval.")

            ready_domains = [
                cart.store_domain.lower()
                for cart in snapshot.store_carts
                if cart.checkout_url
            ]
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

            updated_snapshot = snapshot.model_copy(
                update={
                    "approved_store_domains": resolved_domains,
                    "status": "completed",
                    "current_node": "approval_gate",
                    "current_phase": "checkout",
                    "latest_error": None,
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
        await self.publish(
            SupplementRunEvent(
                event_id=str(uuid4()),
                run_id=run_id,
                event_type="run_completed",
                phase="checkout",
                node_name="approval_gate",
                message="Supplement run is complete and ready for checkout handoff.",
                data={
                    "status": "completed",
                    "approved_store_domains": resolved_domains,
                },
            )
        )
        return supplement_run

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

            supplement_run.status = status
            supplement_run.state_snapshot = _encode_snapshot(state_snapshot)
            await session.commit()


def _encode_snapshot(state_snapshot: Dict[str, object]) -> dict:
    snapshot = SupplementStateSnapshot.model_validate(state_snapshot)
    encoded = jsonable_encoder(snapshot.model_dump(mode="json"))
    trace_metadata = state_snapshot.get("trace_metadata")
    if isinstance(trace_metadata, dict):
        encoded["trace_metadata"] = trace_metadata
    return encoded
