from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


InventoryCategory = Literal["produce", "dairy", "meat", "pantry", "frozen"]


class FridgeItemBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    quantity: float = Field(gt=0)
    unit: Optional[str] = Field(default=None, max_length=32)
    category: InventoryCategory = "pantry"
    expiry_date: Optional[date] = None


class FridgeItemCreate(FridgeItemBase):
    pass


class FridgeItemUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    quantity: Optional[float] = Field(default=None, gt=0)
    unit: Optional[str] = Field(default=None, max_length=32)
    category: Optional[InventoryCategory] = None
    expiry_date: Optional[date] = None


class FridgeItemSnapshot(FridgeItemBase):
    item_id: int
    user_id: str

    model_config = ConfigDict(from_attributes=True)


class FridgeItemRead(FridgeItemSnapshot):
    created_at: datetime
    updated_at: datetime
