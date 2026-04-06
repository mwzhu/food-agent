from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopper.api.deps import get_db_session, get_run_manager
from shopper.models import PlanRun, UserProfile
from shopper.schemas import PlannerStateSnapshot, RunCreateRequest, RunRead, RunTraceRead


router = APIRouter(prefix="/v1/runs", tags=["runs"])


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


@router.post("/{run_id}/resume", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def resume_run(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "detail": "Resume is not available in Phase 3.",
    }
