from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        return stripped
    return value


class ShippingAddress(BaseModel):
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country_code: str = "US"

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("line1", "line2", "city", "state", "postal_code", mode="before")
    @classmethod
    def _normalize_strings(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("country_code", mode="before")
    @classmethod
    def _normalize_country(cls, value: Any) -> str:
        if value is None:
            return "US"
        normalized = str(value).strip().upper()
        return normalized or "US"

    @property
    def is_complete(self) -> bool:
        return bool(self.line1 and self.city and self.state and self.postal_code and self.country_code)


class SupplementBuyerProfileBase(BaseModel):
    email: Optional[str] = None
    shipping_name: Optional[str] = None
    shipping_address: ShippingAddress = Field(default_factory=ShippingAddress)
    billing_same_as_shipping: bool = True
    billing_country: str = "US"
    consent_granted: bool = False
    autopurchase_enabled: bool = False
    max_order_total: Optional[float] = Field(default=None, ge=0)
    max_monthly_total: Optional[float] = Field(default=None, ge=0)
    shop_pay_linked: bool = False
    shop_pay_last_verified_at: Optional[datetime] = None
    last_payment_authorization_at: Optional[datetime] = None
    consent_version: str = "v1"

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("email", "shipping_name", mode="before")
    @classmethod
    def _normalize_optional_strings(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("billing_country", mode="before")
    @classmethod
    def _normalize_billing_country(cls, value: Any) -> str:
        if value is None:
            return "US"
        normalized = str(value).strip().upper()
        return normalized or "US"

    @property
    def is_ready(self) -> bool:
        return bool(self.email and self.shipping_name and self.shipping_address.is_complete and self.consent_granted)


class SupplementBuyerProfileUpsertRequest(SupplementBuyerProfileBase):
    pass


class SupplementBuyerProfileRead(SupplementBuyerProfileBase):
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SupplementBuyerProfileSnapshot(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None
    shipping_name: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_country: Optional[str] = None
    consent_granted: bool = False
    ready: bool = False
    autopurchase_enabled: bool = False
    max_order_total: Optional[float] = None
    max_monthly_total: Optional[float] = None
    shop_pay_linked: bool = False
    last_payment_authorization_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_profile(cls, profile: SupplementBuyerProfileRead) -> "SupplementBuyerProfileSnapshot":
        return cls(
            user_id=profile.user_id,
            email=profile.email,
            shipping_name=profile.shipping_name,
            shipping_city=profile.shipping_address.city,
            shipping_country=profile.shipping_address.country_code,
            consent_granted=profile.consent_granted,
            ready=profile.is_ready,
            autopurchase_enabled=profile.autopurchase_enabled,
            max_order_total=profile.max_order_total,
            max_monthly_total=profile.max_monthly_total,
            shop_pay_linked=profile.shop_pay_linked,
            last_payment_authorization_at=profile.last_payment_authorization_at,
            updated_at=profile.updated_at,
        )
