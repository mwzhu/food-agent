from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from shopper.api.deps import get_browser_profile_manager, get_db_session, get_run_manager
from shopper.models import PlanRun, UserProfile
from shopper.schemas import (
    BrowserProfileSyncSession,
    BrowserProfileSyncStatus,
    CheckoutSmokeRunCreateRequest,
    GroceryItem,
    PlannerStateSnapshot,
    RunRead,
    WalmartSmokeRunCreateRequest,
)
from shopper.schemas.user import UserProfileBase
from shopper.services.browser_profile_manager import (
    BrowserProfileSyncUnavailableError,
    CHATGPT_START_URL,
    INSTACART_GROCERY_START_URL,
    WALMART_GROCERY_START_URL,
)


router = APIRouter(prefix="/v1/checkout", tags=["checkout-profile"])


async def _require_ready_profile(profile_manager, store: str) -> None:
    if store == "walmart":
        status = await profile_manager.get_walmart_status()
    elif store == "instacart":
        status = await profile_manager.get_instacart_status()
    elif store == "chatgpt":
        status = await profile_manager.get_chatgpt_status()
    else:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail="Unsupported checkout profile.")

    if not status.ready:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{status.store} login sync is not ready yet. Finish signing in, close the live session, "
                "then refresh status before starting the run."
            ),
        )


def _walmart_smoke_items() -> list[GroceryItem]:
    return [
        GroceryItem(
            name="bananas",
            quantity=6,
            shopping_quantity=6,
            unit="count",
            category="produce",
        ),
        GroceryItem(
            name="protein bar",
            quantity=1,
            shopping_quantity=1,
            unit="count",
            category="pantry",
        ),
    ]


def _instacart_smoke_items() -> list[GroceryItem]:
    return [
        GroceryItem(
            name="bananas",
            quantity=6,
            shopping_quantity=6,
            unit="count",
            category="produce",
        ),
        GroceryItem(
            name="protein bar",
            quantity=1,
            shopping_quantity=1,
            unit="count",
            category="pantry",
        ),
    ]


def _profile_payload(user: UserProfile) -> UserProfileBase:
    return UserProfileBase.model_validate(
        {field_name: getattr(user, field_name) for field_name in UserProfileBase.model_fields}
    )


@router.get("/walmart/profile-sync", response_model=BrowserProfileSyncStatus)
async def get_walmart_profile_sync_status(
    profile_manager=Depends(get_browser_profile_manager),
) -> BrowserProfileSyncStatus:
    return await profile_manager.get_walmart_status()


@router.post("/walmart/profile-sync/session", response_model=BrowserProfileSyncSession, status_code=status.HTTP_201_CREATED)
async def create_walmart_profile_sync_session(
    profile_manager=Depends(get_browser_profile_manager),
) -> BrowserProfileSyncSession:
    try:
        return await profile_manager.create_walmart_sync_session()
    except BrowserProfileSyncUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/walmart/smoke-run", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def create_walmart_smoke_run(
    payload: WalmartSmokeRunCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_run_manager),
    profile_manager=Depends(get_browser_profile_manager),
) -> RunRead:
    user = await session.get(UserProfile, payload.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    await _require_ready_profile(profile_manager, "walmart")

    run_id = str(uuid4())
    seed_snapshot = PlannerStateSnapshot(
        run_id=run_id,
        user_id=user.user_id,
        user_profile=_profile_payload(user),
        grocery_list=_walmart_smoke_items(),
        status="completed",
    )
    next_state = seed_snapshot.as_checkout_run(
        run_id=run_id,
        store="Walmart",
        start_url=WALMART_GROCERY_START_URL,
    ).model_dump(mode="json")

    checkout_run = PlanRun(
        run_id=run_id,
        user_id=user.user_id,
        status="running",
        state_snapshot=next_state,
    )
    session.add(checkout_run)
    await session.commit()
    await session.refresh(checkout_run)
    run_manager.start_run(run_id=run_id, initial_state=next_state)
    return RunRead.model_validate(checkout_run)


@router.get("/instacart/profile-sync", response_model=BrowserProfileSyncStatus)
async def get_instacart_profile_sync_status(
    profile_manager=Depends(get_browser_profile_manager),
) -> BrowserProfileSyncStatus:
    return await profile_manager.get_instacart_status()


@router.post("/instacart/profile-sync/session", response_model=BrowserProfileSyncSession, status_code=status.HTTP_201_CREATED)
async def create_instacart_profile_sync_session(
    profile_manager=Depends(get_browser_profile_manager),
) -> BrowserProfileSyncSession:
    try:
        return await profile_manager.create_instacart_sync_session()
    except BrowserProfileSyncUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/instacart/smoke-run", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def create_instacart_smoke_run(
    payload: WalmartSmokeRunCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_run_manager),
    profile_manager=Depends(get_browser_profile_manager),
) -> RunRead:
    user = await session.get(UserProfile, payload.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    await _require_ready_profile(profile_manager, "instacart")

    run_id = str(uuid4())
    seed_snapshot = PlannerStateSnapshot(
        run_id=run_id,
        user_id=user.user_id,
        user_profile=_profile_payload(user),
        grocery_list=_instacart_smoke_items(),
        status="completed",
    )
    next_state = seed_snapshot.as_checkout_run(
        run_id=run_id,
        store="Instacart",
        start_url=INSTACART_GROCERY_START_URL,
    ).model_dump(mode="json")

    checkout_run = PlanRun(
        run_id=run_id,
        user_id=user.user_id,
        status="running",
        state_snapshot=next_state,
    )
    session.add(checkout_run)
    await session.commit()
    await session.refresh(checkout_run)
    run_manager.start_run(run_id=run_id, initial_state=next_state)
    return RunRead.model_validate(checkout_run)


@router.get("/chatgpt/profile-sync", response_model=BrowserProfileSyncStatus)
async def get_chatgpt_profile_sync_status(
    profile_manager=Depends(get_browser_profile_manager),
) -> BrowserProfileSyncStatus:
    return await profile_manager.get_chatgpt_status()


@router.post("/chatgpt/profile-sync/session", response_model=BrowserProfileSyncSession, status_code=status.HTTP_201_CREATED)
async def create_chatgpt_profile_sync_session(
    profile_manager=Depends(get_browser_profile_manager),
) -> BrowserProfileSyncSession:
    try:
        return await profile_manager.create_chatgpt_sync_session()
    except BrowserProfileSyncUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/chatgpt/instacart/smoke-run", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def create_chatgpt_instacart_smoke_run(
    payload: CheckoutSmokeRunCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_run_manager),
    profile_manager=Depends(get_browser_profile_manager),
) -> RunRead:
    user = await session.get(UserProfile, payload.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    await _require_ready_profile(profile_manager, "chatgpt")

    run_id = str(uuid4())
    seed_snapshot = PlannerStateSnapshot(
        run_id=run_id,
        user_id=user.user_id,
        user_profile=_profile_payload(user),
        grocery_list=_instacart_smoke_items(),
        status="completed",
    )
    next_state = seed_snapshot.as_checkout_run(
        run_id=run_id,
        store="ChatGPT Instacart",
        start_url=CHATGPT_START_URL,
        allowed_domains=["chatgpt.com", "instacart.com"],
    ).model_dump(mode="json")

    checkout_run = PlanRun(
        run_id=run_id,
        user_id=user.user_id,
        status="running",
        state_snapshot=next_state,
    )
    session.add(checkout_run)
    await session.commit()
    await session.refresh(checkout_run)
    run_manager.start_run(run_id=run_id, initial_state=next_state)
    return RunRead.model_validate(checkout_run)
