from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopper.api.deps import get_db_session
from shopper.models import FridgeItem, UserProfile
from shopper.schemas import FridgeItemCreate, FridgeItemRead, FridgeItemUpdate


router = APIRouter(prefix="/v1/users/{user_id}/inventory", tags=["inventory"])


async def _require_user(session: AsyncSession, user_id: str) -> None:
    user = await session.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")


@router.get("", response_model=list[FridgeItemRead])
async def list_inventory(user_id: str, session: AsyncSession = Depends(get_db_session)) -> list[FridgeItemRead]:
    await _require_user(session, user_id)
    result = await session.execute(
        select(FridgeItem)
        .where(FridgeItem.user_id == user_id)
        .order_by(FridgeItem.category.asc(), FridgeItem.expiry_date.is_(None), FridgeItem.expiry_date.asc(), FridgeItem.name.asc())
    )
    return [FridgeItemRead.model_validate(item) for item in result.scalars().all()]


@router.post("", response_model=FridgeItemRead, status_code=status.HTTP_201_CREATED)
async def create_inventory_item(
    user_id: str,
    payload: FridgeItemCreate,
    session: AsyncSession = Depends(get_db_session),
) -> FridgeItemRead:
    await _require_user(session, user_id)
    item = FridgeItem(user_id=user_id, **payload.model_dump())
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return FridgeItemRead.model_validate(item)


@router.put("/{item_id}", response_model=FridgeItemRead)
async def update_inventory_item(
    user_id: str,
    item_id: int,
    payload: FridgeItemUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> FridgeItemRead:
    await _require_user(session, user_id)
    item = await session.get(FridgeItem, item_id)
    if item is None or item.user_id != user_id:
        raise HTTPException(status_code=404, detail="Inventory item not found.")

    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field_name, value)

    await session.commit()
    await session.refresh(item)
    return FridgeItemRead.model_validate(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inventory_item(
    user_id: str,
    item_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await _require_user(session, user_id)
    item = await session.get(FridgeItem, item_id)
    if item is None or item.user_id != user_id:
        raise HTTPException(status_code=404, detail="Inventory item not found.")

    await session.delete(item)
    await session.commit()
