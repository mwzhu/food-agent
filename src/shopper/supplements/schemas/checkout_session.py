from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


SupplementCheckoutSessionStatus = Literal[
    "pending",
    "awaiting_buyer_profile",
    "preparing_checkout",
    "embedded_ready",
    "agent_running",
    "external_handoff",
    "order_pending_confirmation",
    "order_placed",
    "cancelled",
    "failed",
]
SupplementCheckoutPresentationMode = Literal["iframe", "external", "agent"]


def _normalize_store_domains(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError("store_domains must be a list")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        domain = str(item).strip().lower()
        if not domain or domain in seen:
            continue
        normalized.append(domain)
        seen.add(domain)
    return normalized


class SupplementOrderConfirmationLine(BaseModel):
    title: str
    quantity: int = Field(default=1, ge=1)
    variant_title: Optional[str] = None
    total_amount: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None

    model_config = ConfigDict(str_strip_whitespace=True)


class SupplementOrderConfirmation(BaseModel):
    confirmation_id: str
    store_domain: str
    message: str
    placed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    order_total: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None
    confirmation_url: Optional[str] = None
    line_items: list[SupplementOrderConfirmationLine] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True)


class SupplementCheckoutSessionRead(BaseModel):
    session_id: str
    run_id: str
    store_domain: str
    status: SupplementCheckoutSessionStatus
    checkout_mcp_session_id: Optional[str] = None
    continue_url: Optional[str] = None
    fallback_url: Optional[str] = None
    payment_handlers: list[str] = Field(default_factory=list)
    shop_pay_supported: bool = False
    requires_escalation: bool = False
    presentation_mode: SupplementCheckoutPresentationMode = "iframe"
    embedded_state_payload: dict[str, Any] = Field(default_factory=dict)
    order_confirmation: Optional[SupplementOrderConfirmation] = None
    order_total: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("payment_handlers", mode="before")
    @classmethod
    def _normalize_handlers(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("payment_handlers must be a list")

        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            handler = str(item).strip()
            if not handler or handler in seen:
                continue
            normalized.append(handler)
            seen.add(handler)
        return normalized

    @property
    def is_terminal(self) -> bool:
        return self.status in {"order_placed", "cancelled", "failed"}


class SupplementCheckoutStartRequest(BaseModel):
    store_domains: list[str] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("store_domains", mode="before")
    @classmethod
    def _normalize_domains(cls, value: Any) -> list[str]:
        return _normalize_store_domains(value)


class PaymentCredentials(BaseModel):
    card_number: str = Field(min_length=1)
    card_expiry: str = Field(min_length=1)
    card_cvv: str = Field(min_length=1)
    card_name: str = Field(min_length=1)

    model_config = ConfigDict(str_strip_whitespace=True)


class AgentCheckoutStartRequest(BaseModel):
    store_domains: list[str] = Field(default_factory=list)
    payment_credentials: PaymentCredentials
    simulate_success: bool = False

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("store_domains", mode="before")
    @classmethod
    def _normalize_domains(cls, value: Any) -> list[str]:
        return _normalize_store_domains(value)


class SupplementCheckoutContinueRequest(BaseModel):
    action: Literal["open_fallback", "mark_order_placed"] = "mark_order_placed"
    confirmation_url: Optional[str] = None
    message: Optional[str] = None
    order_total: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None

    model_config = ConfigDict(str_strip_whitespace=True)


class SupplementCheckoutCancelRequest(BaseModel):
    reason: Optional[str] = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("reason", mode="before")
    @classmethod
    def _normalize_reason(cls, value: Any) -> Any:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None
