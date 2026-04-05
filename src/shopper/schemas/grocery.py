from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from shopper.schemas.inventory import InventoryCategory


PurchaseChannel = Literal["online", "in_store"]
PurchaseOrderStatus = Literal["pending", "approved", "purchased", "failed"]


class GroceryItem(BaseModel):
    name: str
    quantity: float = Field(ge=0)
    unit: Optional[str] = None
    category: InventoryCategory = "pantry"
    already_have: bool = False
    shopping_quantity: float = Field(default=0, ge=0)
    quantity_in_fridge: float = Field(default=0, ge=0)
    source_recipe_ids: List[str] = Field(default_factory=list)
    best_store: Optional[str] = None
    best_price: Optional[float] = Field(default=None, ge=0)
    buy_online: Optional[bool] = None


class StoreQuote(BaseModel):
    store: str
    item_name: str
    requested_quantity: float = Field(ge=0)
    requested_unit: Optional[str] = None
    price: float = Field(ge=0)
    unit_price: float = Field(ge=0)
    in_stock: bool = True
    delivery_fee: float = Field(default=0, ge=0)
    min_order: float = Field(default=0, ge=0)


class StoreSummary(BaseModel):
    store: str
    item_count: int = Field(ge=0)
    available_item_count: int = Field(ge=0)
    subtotal: float = Field(ge=0)
    delivery_fee: float = Field(default=0, ge=0)
    total: float = Field(ge=0)
    min_order: float = Field(default=0, ge=0)
    all_items_available: bool = False
    meets_min_order: bool = True


class PurchaseOrderItem(BaseModel):
    name: str
    quantity: float = Field(ge=0)
    unit: Optional[str] = None
    category: InventoryCategory = "pantry"
    source_recipe_ids: List[str] = Field(default_factory=list)
    price: float = Field(ge=0)
    unit_price: float = Field(ge=0)


class PurchaseOrder(BaseModel):
    store: str
    items: List[PurchaseOrderItem] = Field(default_factory=list)
    subtotal: float = Field(ge=0)
    delivery_fee: float = Field(default=0, ge=0)
    total_cost: float = Field(ge=0)
    channel: PurchaseChannel
    status: PurchaseOrderStatus = "pending"


class BudgetSummary(BaseModel):
    budget: float = Field(gt=0)
    total_cost: float = Field(ge=0)
    overage: float = Field(ge=0)
    within_budget: bool
    utilization: float = Field(ge=0)
