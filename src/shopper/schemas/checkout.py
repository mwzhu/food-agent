from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from shopper.schemas.grocery import GroceryItem


PurchaseChannel = Literal["online", "in_store"]
PurchaseOrderStatus = Literal[
    "draft",
    "awaiting_approval",
    "approved",
    "purchased",
    "failed",
    "manual_review",
]
CheckoutStage = Literal[
    "build_cart",
    "awaiting_approval",
    "complete_checkout",
    "completed",
    "manual_review",
]
CheckoutDecision = Literal["approve", "reject"]
CartLineStatus = Literal["added", "missing", "substituted", "removed"]
CheckoutFailureCode = Literal[
    "cart_build_failed",
    "cart_verification_failed",
    "budget_guardrail",
    "login_required",
    "missing_payment_method",
    "payment_declined",
    "address_required",
    "delivery_slot_required",
    "bot_protection",
    "checkout_navigation_failed",
    "unknown",
]


class CheckoutStoreConfig(BaseModel):
    store: str
    start_url: str
    cart_url: Optional[str] = None
    checkout_url: Optional[str] = None
    allowed_domains: List[str] = Field(default_factory=list)


class CartLineItem(BaseModel):
    requested_name: str
    requested_quantity: float = Field(ge=0)
    actual_name: str
    actual_quantity: float = Field(ge=0)
    unit: Optional[str] = None
    unit_price: float = Field(default=0, ge=0)
    line_total: float = Field(default=0, ge=0)
    status: CartLineStatus = "added"
    notes: str = ""
    product_url: Optional[str] = None


class AppliedCoupon(BaseModel):
    code: str
    description: str = ""
    amount: float = Field(default=0, ge=0)


class CartDiscrepancy(BaseModel):
    code: str
    message: str
    item_name: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None


class CartVerification(BaseModel):
    passed: bool
    discrepancies: List[CartDiscrepancy] = Field(default_factory=list)
    subtotal_expected: Optional[float] = Field(default=None, ge=0)
    subtotal_actual: Optional[float] = Field(default=None, ge=0)
    delivery_fee_expected: Optional[float] = Field(default=None, ge=0)
    delivery_fee_actual: Optional[float] = Field(default=None, ge=0)


class CartBuildResult(BaseModel):
    store: str
    store_url: str
    items: List[CartLineItem] = Field(default_factory=list)
    subtotal: float = Field(default=0, ge=0)
    delivery_fee: float = Field(default=0, ge=0)
    total_cost: float = Field(default=0, ge=0)
    cart_url: Optional[str] = None
    cart_screenshot_path: Optional[str] = None
    coupons: List[AppliedCoupon] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    raw_response: Dict[str, Any] = Field(default_factory=dict)


class OrderConfirmation(BaseModel):
    confirmation_id: str
    placed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_cost: float = Field(ge=0)
    confirmation_url: Optional[str] = None
    confirmation_screenshot_path: Optional[str] = None
    message: str = ""


class PurchaseOrder(BaseModel):
    order_id: str
    store: str
    store_url: str
    channel: PurchaseChannel = "online"
    status: PurchaseOrderStatus = "draft"
    items: List[CartLineItem] = Field(default_factory=list)
    requested_items: List[GroceryItem] = Field(default_factory=list)
    subtotal: float = Field(default=0, ge=0)
    delivery_fee: float = Field(default=0, ge=0)
    total_cost: float = Field(default=0, ge=0)
    coupons: List[AppliedCoupon] = Field(default_factory=list)
    verification: Optional[CartVerification] = None
    cart_url: Optional[str] = None
    checkout_url: Optional[str] = None
    allowed_domains: List[str] = Field(default_factory=list)
    cart_screenshot_path: Optional[str] = None
    confirmation: Optional[OrderConfirmation] = None
    failure_code: Optional[CheckoutFailureCode] = None
    failure_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CheckoutItemEdit(BaseModel):
    requested_name: str
    quantity: Optional[float] = Field(default=None, ge=0)
    remove: bool = False


class CheckoutRunCreateRequest(BaseModel):
    store: str
    start_url: str
    cart_url: Optional[str] = None
    checkout_url: Optional[str] = None
    allowed_domains: List[str] = Field(default_factory=list)


class BrowserProfileSyncStatus(BaseModel):
    store: str
    provider: Literal["browser_use_cloud", "local_browser"] = "browser_use_cloud"
    configured: bool
    ready: bool
    profile_id: Optional[str] = None
    profile_name: Optional[str] = None
    login_url: str
    start_url: str
    cookie_domains: List[str] = Field(default_factory=list)
    last_used_at: Optional[datetime] = None
    message: str = ""


class BrowserProfileSyncSession(BaseModel):
    store: str
    provider: Literal["browser_use_cloud", "local_browser"] = "browser_use_cloud"
    profile_id: str
    session_id: str
    live_url: str
    login_url: str
    timeout_at: datetime
    message: str = ""


class CheckoutResumeRequest(BaseModel):
    decision: CheckoutDecision
    reason: Optional[str] = None
    edits: List[CheckoutItemEdit] = Field(default_factory=list)


class StandaloneCheckoutRequest(BaseModel):
    user_id: str = "standalone"
    store: CheckoutStoreConfig
    items: List[GroceryItem]
    approve: bool = False
    headless: bool = True
    max_steps: int = Field(default=80, ge=1, le=500)


class StandaloneCheckoutResult(BaseModel):
    order: PurchaseOrder
    status: Literal["awaiting_approval", "completed", "failed"]
    approval_required: bool
    notes: List[str] = Field(default_factory=list)
