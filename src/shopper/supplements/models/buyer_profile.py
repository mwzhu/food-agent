from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from shopper.models.base import Base


class SupplementBuyerProfile(Base):
    __tablename__ = "supplement_buyer_profiles"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    shipping_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    shipping_address_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    billing_same_as_shipping: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    billing_country: Mapped[str] = mapped_column(String(8), default="US", nullable=False)
    consent_granted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    autopurchase_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_order_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_monthly_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    shop_pay_linked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    shop_pay_last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_payment_authorization_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_version: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
