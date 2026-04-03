from __future__ import annotations

from typing import Optional

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shopper.models import FridgeItem
from shopper.schemas import FridgeItemRead


def build_get_fridge_contents_tool(session_factory: Optional[async_sessionmaker[AsyncSession]]):
    @tool("get_fridge_contents")
    async def get_fridge_contents(user_id: str) -> list[dict]:
        """Return the user's fridge inventory."""
        if session_factory is None:
            return []

        async with session_factory() as session:
            result = await session.execute(
                select(FridgeItem)
                .where(FridgeItem.user_id == user_id)
                .order_by(FridgeItem.category.asc(), FridgeItem.name.asc())
            )
            items = result.scalars().all()

        return [FridgeItemRead.model_validate(item).model_dump(mode="json") for item in items]

    return get_fridge_contents
