from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from shopper.schemas.inventory import InventoryCategory


class GroceryItem(BaseModel):
    name: str
    quantity: float = Field(ge=0)
    unit: Optional[str] = None
    category: InventoryCategory = "pantry"
    already_have: bool = False
    shopping_quantity: float = Field(default=0, ge=0)
    quantity_in_fridge: float = Field(default=0, ge=0)
    source_recipe_ids: List[str] = Field(default_factory=list)
