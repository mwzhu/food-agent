from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from shopper.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("plan_runs.run_id"), index=True, nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("user_profiles.user_id"), index=True)
    agent: Mapped[str] = mapped_column(String(128), nullable=False, default="planner")
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    phase: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    node_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    input_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    screenshot_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
