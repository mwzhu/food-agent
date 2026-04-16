from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from shopper.models.base import Base


class SupplementCheckoutSession(Base):
    __tablename__ = "supplement_checkout_sessions"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("supplement_runs.run_id"), index=True, nullable=False)
    store_domain: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    checkout_mcp_session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(48), default="pending", index=True, nullable=False)
    continue_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    fallback_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    payment_handlers_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    shop_pay_supported: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_escalation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    presentation_mode: Mapped[str] = mapped_column(String(24), default="iframe", nullable=False)
    embedded_state_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    order_confirmation_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    order_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
