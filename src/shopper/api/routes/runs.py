from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopper.agents.tools import BrowserCheckoutAgent
from shopper.api.deps import get_browser_profile_manager, get_db_session, get_run_manager
from shopper.models import PlanRun, UserProfile
from shopper.schemas import (
    CheckoutRunCreate,
    PlannerStateSnapshot,
    PurchaseOrder,
    RunCreateRequest,
    RunEvent,
    RunRead,
    RunResumeRequest,
    RunTraceRead,
)


router = APIRouter(prefix="/v1/runs", tags=["runs"])


async def _require_ready_checkout_profile(profile_manager, payload: CheckoutRunCreate) -> None:
    start_url = (payload.start_url or "").lower()
    store = payload.store.lower()

    if "instacart" in store or "instacart" in start_url:
        status = await profile_manager.get_instacart_status()
    elif "chatgpt" in store or "chatgpt.com" in start_url:
        status = await profile_manager.get_chatgpt_status()
    else:
        return

    if not status.ready:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{status.store} login sync is not ready yet. Finish signing in, close the live session, "
                "then refresh status before starting checkout."
            ),
        )


@router.get("", response_model=list[RunRead])
async def list_runs(
    user_id: str = Query(..., min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_db_session),
) -> list[RunRead]:
    result = await session.execute(
        select(PlanRun).where(PlanRun.user_id == user_id).order_by(PlanRun.created_at.desc()).limit(limit)
    )
    runs = result.scalars().all()
    return [RunRead.model_validate(run) for run in runs]


@router.post("", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: RunCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_run_manager),
) -> RunRead:
    profile = payload.profile.model_dump(mode="json")
    user = await session.get(UserProfile, payload.user_id)
    if user is None:
        user = UserProfile(user_id=payload.user_id, **profile)
        session.add(user)
    else:
        for field_name, value in profile.items():
            setattr(user, field_name, value)
    await session.commit()

    run_id = str(uuid4())
    initial_state = PlannerStateSnapshot.starting(
        run_id=run_id,
        user_id=payload.user_id,
        user_profile=profile,
    ).model_dump(mode="json")

    plan_run = PlanRun(run_id=run_id, user_id=payload.user_id, status="running", state_snapshot=initial_state)
    session.add(plan_run)
    await session.commit()
    await session.refresh(plan_run)
    run_manager.start_run(run_id=run_id, initial_state=initial_state)
    return RunRead.model_validate(plan_run)


@router.get("/{run_id}", response_model=RunRead)
async def get_run(run_id: str, session: AsyncSession = Depends(get_db_session)) -> RunRead:
    plan_run = await session.get(PlanRun, run_id)
    if plan_run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return RunRead.model_validate(plan_run)


@router.get("/{run_id}/trace", response_model=RunTraceRead)
async def get_run_trace(run_id: str, session: AsyncSession = Depends(get_db_session)) -> RunTraceRead:
    plan_run = await session.get(PlanRun, run_id)
    if plan_run is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    snapshot = PlannerStateSnapshot.model_validate(plan_run.state_snapshot)
    return RunTraceRead(
        run_id=run_id,
        kind=snapshot.trace_metadata.kind,
        project=snapshot.trace_metadata.project,
        trace_id=snapshot.trace_metadata.trace_id,
        source=snapshot.trace_metadata.source,
        url=None,
    )


@router.post("/{run_id}/shopping", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def create_shopping_run(
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_run_manager),
) -> RunRead:
    source_run = await session.get(PlanRun, run_id)
    if source_run is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    snapshot = PlannerStateSnapshot.model_validate(source_run.state_snapshot)
    if not snapshot.selected_meals:
        raise HTTPException(status_code=400, detail="A meal plan is required before shopping can start.")

    next_run_id = str(uuid4())
    next_state = snapshot.as_shopping_run(run_id=next_run_id).model_dump(mode="json")
    shopping_run = PlanRun(
        run_id=next_run_id,
        user_id=source_run.user_id,
        status="running",
        state_snapshot=next_state,
    )
    session.add(shopping_run)
    await session.commit()
    await session.refresh(shopping_run)
    run_manager.start_run(run_id=next_run_id, initial_state=next_state)
    return RunRead.model_validate(shopping_run)


@router.post("/{run_id}/checkout", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def create_checkout_run(
    run_id: str,
    payload: CheckoutRunCreate,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_run_manager),
    profile_manager=Depends(get_browser_profile_manager),
) -> RunRead:
    source_run = await session.get(PlanRun, run_id)
    if source_run is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    snapshot = PlannerStateSnapshot.model_validate(source_run.state_snapshot)
    if not snapshot.grocery_list:
        raise HTTPException(status_code=400, detail="A grocery list is required before checkout can start.")
    await _require_ready_checkout_profile(profile_manager, payload)

    next_run_id = str(uuid4())
    next_state = snapshot.as_checkout_run(
        run_id=next_run_id,
        store=payload.store,
        start_url=payload.start_url,
        cart_url=payload.cart_url,
        checkout_url=payload.checkout_url,
        allowed_domains=payload.allowed_domains,
    ).model_dump(mode="json")
    checkout_run = PlanRun(
        run_id=next_run_id,
        user_id=source_run.user_id,
        status="running",
        state_snapshot=next_state,
    )
    session.add(checkout_run)
    await session.commit()
    await session.refresh(checkout_run)
    run_manager.start_run(run_id=next_run_id, initial_state=next_state)
    return RunRead.model_validate(checkout_run)


@router.post("/{run_id}/resume", response_model=RunRead)
async def resume_run(
    run_id: str,
    payload: RunResumeRequest,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_run_manager),
) -> RunRead:
    plan_run = await session.get(PlanRun, run_id)
    if plan_run is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    snapshot = PlannerStateSnapshot.model_validate(plan_run.state_snapshot)
    if snapshot.status != "awaiting_approval" or snapshot.current_phase != "checkout":
        raise HTTPException(status_code=409, detail="Run is not waiting for checkout approval.")
    if not snapshot.purchase_orders:
        raise HTTPException(status_code=409, detail="Checkout run does not have a prepared order.")

    order = PurchaseOrder.model_validate(snapshot.purchase_orders[0])
    if payload.edits:
        order = BrowserCheckoutAgent(run_manager.settings).apply_edits(order, payload.edits)

    if payload.decision == "reject":
        rejected_snapshot = snapshot.model_copy(
            update={
                "status": "failed",
                "human_approved": False,
                "approval_reason": payload.reason,
                "purchase_orders": [
                    order.model_copy(
                        update={
                            "status": "failed",
                            "failure_reason": payload.reason or "Checkout was rejected by the user.",
                        }
                    )
                ],
                "current_phase": "checkout",
                "current_node": "approval_gate",
                "checkout_stage": "manual_review",
                "phase_statuses": snapshot.phase_statuses.model_copy(update={"checkout": "failed"}),
                "latest_error": payload.reason or "Checkout was rejected by the user.",
            }
        )
        plan_run.status = rejected_snapshot.status
        plan_run.state_snapshot = rejected_snapshot.model_dump(mode="json")
        await session.commit()
        await run_manager.publish(
            RunEvent(
                event_id=str(uuid4()),
                run_id=run_id,
                event_type="approval_resolved",
                phase="checkout",
                node_name="approval_gate",
                message="Checkout was rejected.",
                data={"decision": "reject", "reason": payload.reason},
            )
        )
        await run_manager.publish(
            RunEvent(
                event_id=str(uuid4()),
                run_id=run_id,
                event_type="run_completed",
                phase="checkout",
                node_name="approval_gate",
                message="Checkout run failed after rejection.",
                data={"status": "failed"},
            )
        )
        await run_manager.persist_run_events(run_id)
        await session.refresh(plan_run)
        return RunRead.model_validate(plan_run)

    resumed_snapshot = snapshot.model_copy(
        update={
            "status": "running",
            "human_approved": True,
            "approval_reason": payload.reason,
            "purchase_orders": [order.model_copy(update={"status": "approved"})],
            "current_phase": "checkout",
            "current_node": "approval_gate",
            "checkout_stage": "complete_checkout",
            "phase_statuses": snapshot.phase_statuses.model_copy(update={"checkout": "running"}),
            "latest_error": None,
        }
    )
    plan_run.status = resumed_snapshot.status
    plan_run.state_snapshot = resumed_snapshot.model_dump(mode="json")
    await session.commit()
    await run_manager.publish(
        RunEvent(
            event_id=str(uuid4()),
            run_id=run_id,
            event_type="approval_resolved",
            phase="checkout",
            node_name="approval_gate",
            message="Checkout was approved and is resuming.",
            data={"decision": "approve", "reason": payload.reason},
        )
    )
    run_manager.start_run(run_id=run_id, initial_state=resumed_snapshot.model_dump(mode="json"))
    await session.refresh(plan_run)
    return RunRead.model_validate(plan_run)
