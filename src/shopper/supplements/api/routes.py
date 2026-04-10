from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from shopper.api.deps import get_db_session, get_supplement_run_manager
from shopper.supplements.models import SupplementRun
from shopper.supplements.schemas import (
    SupplementRunApproveRequest,
    SupplementRunCreateRequest,
    SupplementRunEvent,
    SupplementRunRead,
    SupplementStateSnapshot,
)


router = APIRouter(prefix="/v1/supplements/runs", tags=["supplements"])


@router.post("", response_model=SupplementRunRead, status_code=status.HTTP_201_CREATED)
async def create_supplement_run(
    payload: SupplementRunCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_supplement_run_manager),
) -> SupplementRunRead:
    run_id = str(uuid4())
    initial_state = SupplementStateSnapshot.starting(
        run_id=run_id,
        user_id=payload.user_id,
        health_profile=payload.health_profile.model_dump(mode="json"),
    ).model_dump(mode="json")

    supplement_run = SupplementRun(
        run_id=run_id,
        user_id=payload.user_id,
        status="running",
        state_snapshot=initial_state,
    )
    session.add(supplement_run)
    await session.commit()
    await session.refresh(supplement_run)

    run_manager.start_run(run_id=run_id, initial_state=initial_state)
    return SupplementRunRead.model_validate(supplement_run)


@router.get("/{run_id}", response_model=SupplementRunRead)
async def get_supplement_run(
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> SupplementRunRead:
    supplement_run = await session.get(SupplementRun, run_id)
    if supplement_run is None:
        raise HTTPException(status_code=404, detail="Supplement run not found.")
    return SupplementRunRead.model_validate(supplement_run)


@router.get("/{run_id}/stream")
async def stream_supplement_run_events(
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_supplement_run_manager),
):
    supplement_run = await session.get(SupplementRun, run_id)
    if supplement_run is None:
        raise HTTPException(status_code=404, detail="Supplement run not found.")

    snapshot = SupplementStateSnapshot.model_validate(supplement_run.state_snapshot)

    async def event_stream():
        cursor = 0
        events = run_manager.event_bus.list_events(run_id)
        if not events and snapshot.status != "running":
            if snapshot.status == "awaiting_approval":
                event_type = "approval_requested"
                message = "Checkout links are ready for approval."
            elif snapshot.status == "completed":
                event_type = "run_completed"
                message = "Supplement run completed."
            else:
                event_type = "error"
                message = "Supplement run failed."
            events = [
                SupplementRunEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    event_type=event_type,
                    message=message,
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

            if snapshot.status in {"completed", "failed"}:
                return
            yield ": keep-alive\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{run_id}/approve", response_model=SupplementRunRead)
async def approve_supplement_run(
    run_id: str,
    payload: SupplementRunApproveRequest,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_supplement_run_manager),
) -> SupplementRunRead:
    try:
        supplement_run = await run_manager.approve_run(
            run_id=run_id,
            approved_store_domains=payload.approved_store_domains,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    refreshed_run = await session.get(SupplementRun, supplement_run.run_id)
    assert refreshed_run is not None
    return SupplementRunRead.model_validate(refreshed_run)


def _format_sse(event: SupplementRunEvent) -> str:
    payload = json.dumps(event.model_dump(mode="json"))
    return "event: {event_type}\ndata: {payload}\n\n".format(
        event_type=event.event_type,
        payload=payload,
    )
