from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from shopper.api.deps import get_db_session
from shopper.models import UserProfile
from shopper.schemas import UserProfileCreate, UserProfileRead, UserProfileUpdate


router = APIRouter(prefix="/v1/users", tags=["users"])


@router.post("", response_model=UserProfileRead, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserProfileCreate, session: AsyncSession = Depends(get_db_session)) -> UserProfileRead:
    existing_user = await session.get(UserProfile, payload.user_id)
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="User already exists.")

    user = UserProfile(**payload.model_dump())
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return UserProfileRead.model_validate(user)


@router.get("/{user_id}", response_model=UserProfileRead)
async def get_user(user_id: str, session: AsyncSession = Depends(get_db_session)) -> UserProfileRead:
    user = await session.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return UserProfileRead.model_validate(user)


@router.put("/{user_id}", response_model=UserProfileRead)
async def update_user(
    user_id: str,
    payload: UserProfileUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> UserProfileRead:
    user = await session.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field_name, value)

    await session.commit()
    await session.refresh(user)
    return UserProfileRead.model_validate(user)
