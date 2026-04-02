from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from shopper.api.deps import get_db_session, get_run_manager
from shopper.models import PlanRun
from shopper.schemas import PlannerStateSnapshot, RunEvent


router = APIRouter(prefix="/v1/runs", tags=["run-stream"])


@router.get("/{run_id}/stream")
async def stream_run_events(
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_run_manager),
):
    plan_run = await session.get(PlanRun, run_id)
    if plan_run is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    snapshot = PlannerStateSnapshot.model_validate(plan_run.state_snapshot)

    async def event_stream():
        cursor = 0
        events = run_manager.event_bus.list_events(run_id)
        if not events and snapshot.status != "running":
            event_type = "run_completed" if snapshot.status == "completed" else "error"
            events = [
                RunEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    event_type=event_type,
                    message="Run {status}.".format(status=snapshot.status),
                    phase=snapshot.current_phase,
                    node_name=snapshot.current_node,
                    data={"status": snapshot.status},
                )
            ]

        for event in events:
            cursor += 1
            yield _format_sse(event)

        while True:
            new_events = await run_manager.event_bus.wait_for_events(run_id, cursor, timeout=1.0)
            if new_events:
                for event in new_events:
                    cursor += 1
                    yield _format_sse(event)
                    if event.event_type in {"run_completed", "error"}:
                        return
                continue

            yield ": keep-alive\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _format_sse(event: RunEvent) -> str:
    payload = json.dumps(event.model_dump(mode="json"))
    return "event: {event_type}\ndata: {payload}\n\n".format(
        event_type=event.event_type,
        payload=payload,
    )
