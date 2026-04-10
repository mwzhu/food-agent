from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shopper.supplements.schemas.product import ShopifyProduct


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class StackItem(BaseModel):
    category: str
    goal: str
    product: ShopifyProduct
    quantity: int = Field(default=1, ge=1)
    dosage: str = ""
    cadence: str = ""
    monthly_cost: Optional[float] = None
    rationale: str = ""
    cautions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("monthly_cost", mode="before")
    @classmethod
    def _coerce_monthly_cost(cls, value: Any) -> Any:
        return _blank_to_none(value)


class SupplementStack(BaseModel):
    summary: str = ""
    items: list[StackItem] = Field(default_factory=list)
    total_monthly_cost: Optional[float] = None
    currency: str = "USD"
    within_budget: Optional[bool] = None
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("total_monthly_cost", mode="before")
    @classmethod
    def _coerce_total_monthly_cost(cls, value: Any) -> Any:
        return _blank_to_none(value)


class StoreCartLine(BaseModel):
    line_id: str = ""
    product_id: str
    product_title: str
    variant_id: str
    variant_title: str = ""
    quantity: int = Field(default=1, ge=1)
    subtotal_amount: Optional[float] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("subtotal_amount", "total_amount", mode="before")
    @classmethod
    def _coerce_amounts(cls, value: Any) -> Any:
        return _blank_to_none(value)


class StoreCart(BaseModel):
    store_domain: str
    cart_id: Optional[str] = None
    checkout_url: Optional[str] = None
    total_quantity: int = Field(default=0, ge=0)
    subtotal_amount: Optional[float] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = None
    lines: list[StoreCartLine] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    instructions: Optional[str] = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("subtotal_amount", "total_amount", mode="before")
    @classmethod
    def _coerce_amounts(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @classmethod
    def from_mcp(cls, cart: Any) -> "StoreCart":
        return cls(
            store_domain=getattr(cart, "store_domain", ""),
            cart_id=getattr(cart, "cart_id", None),
            checkout_url=getattr(cart, "checkout_url", None),
            total_quantity=int(getattr(cart, "total_quantity", 0) or 0),
            subtotal_amount=getattr(cart, "subtotal_amount", None),
            total_amount=getattr(cart, "total_amount", None),
            currency=getattr(cart, "currency", None),
            lines=[
                StoreCartLine(
                    line_id=getattr(line, "line_id", ""),
                    product_id=getattr(line, "product_id", ""),
                    product_title=getattr(line, "product_title", ""),
                    variant_id=getattr(line, "variant_id", ""),
                    variant_title=getattr(line, "variant_title", ""),
                    quantity=int(getattr(line, "quantity", 1) or 1),
                    subtotal_amount=getattr(line, "subtotal_amount", None),
                    total_amount=getattr(line, "total_amount", None),
                    currency=getattr(line, "currency", None),
                )
                for line in (getattr(cart, "lines", []) or [])
            ],
            errors=list(getattr(cart, "errors", []) or []),
            instructions=getattr(cart, "instructions", None),
        )
