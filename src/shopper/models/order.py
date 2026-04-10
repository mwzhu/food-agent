from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from shopper.models.base import Base


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("plan_runs.run_id"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("user_profiles.user_id"), index=True, nullable=False)
    store: Mapped[str] = mapped_column(String(255), nullable=False)
    store_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="online")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    subtotal: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    delivery_fee: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    total_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    cart_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    checkout_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    cart_screenshot_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    verification_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    confirmation_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("purchase_orders.order_id"), index=True, nullable=False)
    requested_name: Mapped[str] = mapped_column(String(255), nullable=False)
    actual_name: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    actual_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    unit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    line_total: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="added")
    notes: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    product_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
