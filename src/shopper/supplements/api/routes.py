from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from shopper.api.deps import get_db_session, get_settings, get_supplement_run_manager
from shopper.config import Settings
from shopper.supplements.models import SupplementRun
from shopper.supplements.schemas import (
    AgentCheckoutStartRequest,
    SupplementCartUpdateRequest,
    SupplementBuyerProfileRead,
    SupplementBuyerProfileUpsertRequest,
    SupplementCheckoutCancelRequest,
    SupplementCheckoutEmbedSpikeRead,
    SupplementCheckoutEmbedSpikeRequest,
    SupplementCheckoutContinueRequest,
    SupplementCheckoutSessionRead,
    SupplementCheckoutStartRequest,
    SupplementRunApproveRequest,
    SupplementRunCreateRequest,
    SupplementRunEvent,
    SupplementRunRead,
    SupplementStateSnapshot,
)
from shopper.supplements.services.checkout_embed_probe import CheckoutEmbedProbeService
from shopper.supplements.tools.shopify_mcp import ShopifyMCPClient, ShopifyMCPError


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
        supplement_run = await run_manager.approve_stores(
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


@router.post("/{run_id}/buyer-profile", response_model=SupplementBuyerProfileRead)
async def upsert_supplement_buyer_profile(
    run_id: str,
    payload: SupplementBuyerProfileUpsertRequest,
    run_manager=Depends(get_supplement_run_manager),
) -> SupplementBuyerProfileRead:
    try:
        return await run_manager.upsert_buyer_profile(run_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{run_id}/buyer-profile", response_model=SupplementBuyerProfileRead)
async def get_supplement_buyer_profile(
    run_id: str,
    run_manager=Depends(get_supplement_run_manager),
) -> SupplementBuyerProfileRead:
    try:
        buyer_profile = await run_manager.get_buyer_profile(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if buyer_profile is None:
        raise HTTPException(status_code=404, detail="Buyer profile not found.")
    return buyer_profile


@router.post("/{run_id}/approve-stores", response_model=SupplementRunRead)
async def approve_supplement_stores(
    run_id: str,
    payload: SupplementRunApproveRequest,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_supplement_run_manager),
) -> SupplementRunRead:
    try:
        supplement_run = await run_manager.approve_stores(
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


@router.post("/{run_id}/cart/quantities", response_model=SupplementRunRead)
async def update_supplement_cart_quantities(
    run_id: str,
    payload: SupplementCartUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_supplement_run_manager),
) -> SupplementRunRead:
    try:
        supplement_run = await run_manager.update_cart_quantities(run_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    refreshed_run = await session.get(SupplementRun, supplement_run.run_id)
    assert refreshed_run is not None
    return SupplementRunRead.model_validate(refreshed_run)


@router.post("/{run_id}/checkout/start", response_model=SupplementRunRead)
async def start_supplement_checkout(
    run_id: str,
    payload: SupplementCheckoutStartRequest,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_supplement_run_manager),
) -> SupplementRunRead:
    try:
        supplement_run = await run_manager.start_checkout(run_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    refreshed_run = await session.get(SupplementRun, supplement_run.run_id)
    assert refreshed_run is not None
    return SupplementRunRead.model_validate(refreshed_run)


@router.post("/{run_id}/checkout/agent-start", response_model=SupplementRunRead)
async def start_agent_checkout(
    run_id: str,
    payload: AgentCheckoutStartRequest,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_supplement_run_manager),
) -> SupplementRunRead:
    try:
        supplement_run = await run_manager.start_agent_checkout(run_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    refreshed_run = await session.get(SupplementRun, supplement_run.run_id)
    assert refreshed_run is not None
    return SupplementRunRead.model_validate(refreshed_run)


@router.get("/{run_id}/checkout/{store_domain}", response_model=SupplementCheckoutSessionRead)
async def get_supplement_checkout_session(
    run_id: str,
    store_domain: str,
    run_manager=Depends(get_supplement_run_manager),
) -> SupplementCheckoutSessionRead:
    try:
        return await run_manager.get_checkout_session(run_id, store_domain)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{run_id}/checkout/{store_domain}/continue", response_model=SupplementRunRead)
async def continue_supplement_checkout(
    run_id: str,
    store_domain: str,
    payload: SupplementCheckoutContinueRequest,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_supplement_run_manager),
) -> SupplementRunRead:
    try:
        supplement_run = await run_manager.continue_checkout(run_id, store_domain, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    refreshed_run = await session.get(SupplementRun, supplement_run.run_id)
    assert refreshed_run is not None
    return SupplementRunRead.model_validate(refreshed_run)


@router.post("/{run_id}/checkout/{store_domain}/cancel", response_model=SupplementRunRead)
async def cancel_supplement_checkout(
    run_id: str,
    store_domain: str,
    payload: SupplementCheckoutCancelRequest,
    session: AsyncSession = Depends(get_db_session),
    run_manager=Depends(get_supplement_run_manager),
) -> SupplementRunRead:
    try:
        supplement_run = await run_manager.cancel_checkout(run_id, store_domain, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    refreshed_run = await session.get(SupplementRun, supplement_run.run_id)
    assert refreshed_run is not None
    return SupplementRunRead.model_validate(refreshed_run)


@router.post("/checkout/embed-spike", response_model=SupplementCheckoutEmbedSpikeRead)
async def run_supplement_checkout_embed_spike(
    payload: SupplementCheckoutEmbedSpikeRequest,
    settings: Settings = Depends(get_settings),
) -> SupplementCheckoutEmbedSpikeRead:
    async with ShopifyMCPClient() as client:
        try:
            products = await client.search_store(payload.store_domain, payload.query)
        except ShopifyMCPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        selected_product = None
        selected_variant = None
        for product in products[:8]:
            available_variants = [variant for variant in product.variants if variant.available]
            if available_variants:
                selected_product = product
                selected_variant = available_variants[0]
                break

        if selected_product is None or selected_variant is None:
            raise HTTPException(status_code=409, detail="No in-stock variant was available for the embed spike.")

        try:
            cart = await client.update_cart(payload.store_domain, selected_variant.variant_id, 1)
        except ShopifyMCPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    embed_probe_service = CheckoutEmbedProbeService(settings)
    try:
        embed_probe = await embed_probe_service.probe_checkout_url(cart.checkout_url or "")
    finally:
        await embed_probe_service.aclose()

    return SupplementCheckoutEmbedSpikeRead(
        store_domain=payload.store_domain,
        query=payload.query,
        selected_product_title=selected_product.title,
        selected_variant_id=selected_variant.variant_id,
        checkout_url=cart.checkout_url,
        final_url=embed_probe.final_url,
        status_code=embed_probe.status_code,
        iframe_allowed=embed_probe.iframe_allowed,
        block_reason=embed_probe.block_reason,
        x_frame_options=embed_probe.x_frame_options,
        content_security_policy=embed_probe.content_security_policy,
        frame_ancestors=embed_probe.frame_ancestors,
        allowed_embed_origins=embed_probe.allowed_embed_origins,
        error=embed_probe.error,
    )


def _format_sse(event: SupplementRunEvent) -> str:
    payload = json.dumps(event.model_dump(mode="json"))
    return "event: {event_type}\ndata: {payload}\n\n".format(
        event_type=event.event_type,
        payload=payload,
    )
