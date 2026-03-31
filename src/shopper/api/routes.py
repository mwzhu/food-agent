from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from shopper.orchestrator import RunOrchestrator
from shopper.schemas import BootstrapSessionRequest, FeedbackRequest, ResumeRequest, RunInput, RunResponse


router = APIRouter(prefix="/v1", tags=["runs"])


def get_orchestrator(request: Request) -> RunOrchestrator:
    return request.app.state.orchestrator


def get_session_factory(request: Request):
    return request.app.state.session_factory


async def get_db_session(request: Request):
    async with request.app.state.session_factory() as session:
        yield session


@router.post("/runs", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: RunInput,
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
    session: AsyncSession = Depends(get_db_session),
) -> RunResponse:
    return await orchestrator.start_run(session, payload)


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
    session: AsyncSession = Depends(get_db_session),
) -> RunResponse:
    try:
        return await orchestrator.get_run(session, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=f"Run not found: {exc.args[0]}") from exc


@router.post("/runs/{run_id}/resume", response_model=RunResponse)
async def resume_run(
    run_id: str,
    payload: ResumeRequest,
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
    session: AsyncSession = Depends(get_db_session),
) -> RunResponse:
    try:
        return await orchestrator.resume_run(session, run_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=f"Run not found: {exc.args[0]}") from exc


@router.post("/feedback", status_code=status.HTTP_202_ACCEPTED)
async def create_feedback(
    payload: FeedbackRequest,
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await orchestrator.record_feedback(session, payload)
    return {"status": "accepted"}


@router.post("/integrations/walmart/session/bootstrap", status_code=status.HTTP_202_ACCEPTED)
async def bootstrap_walmart_session(
    payload: BootstrapSessionRequest,
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await orchestrator.bootstrap_session(session, payload.user_id, payload.profile_id, payload.metadata)
    return {"status": "accepted"}
