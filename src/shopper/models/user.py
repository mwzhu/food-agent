from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from shopper.models.base import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_lbs: Mapped[float] = mapped_column(Float, nullable=False)
    height_in: Mapped[float] = mapped_column(Float, nullable=False)
    sex: Mapped[str] = mapped_column(String(16), nullable=False)
    activity_level: Mapped[str] = mapped_column(String(32), nullable=False)
    goal: Mapped[str] = mapped_column(String(16), nullable=False)
    dietary_restrictions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    allergies: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    budget_weekly: Mapped[float] = mapped_column(Float, default=150.0, nullable=False)
    household_size: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cooking_skill: Mapped[str] = mapped_column(String(32), default="intermediate", nullable=False)
    schedule_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
