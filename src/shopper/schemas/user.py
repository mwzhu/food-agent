from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class UserProfileBase(BaseModel):
    age: int = Field(ge=13, le=120)
    weight_lbs: float = Field(gt=0)
    height_in: float = Field(gt=0)
    sex: Literal["female", "male", "other"]
    activity_level: Literal[
        "sedentary",
        "lightly_active",
        "moderately_active",
        "very_active",
        "extra_active",
    ]
    goal: Literal["cut", "maintain", "bulk"]
    dietary_restrictions: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    budget_weekly: float = Field(default=150.0, gt=0)
    household_size: int = Field(default=1, ge=1)
    cooking_skill: Literal["beginner", "intermediate", "advanced"] = "intermediate"
    schedule_json: Dict[str, Any] = Field(default_factory=dict)


class UserProfileCreate(UserProfileBase):
    user_id: str = Field(min_length=1, max_length=64)


class UserProfileUpdate(BaseModel):
    age: Optional[int] = Field(default=None, ge=13, le=120)
    weight_lbs: Optional[float] = Field(default=None, gt=0)
    height_in: Optional[float] = Field(default=None, gt=0)
    sex: Optional[Literal["female", "male", "other"]] = None
    activity_level: Optional[
        Literal["sedentary", "lightly_active", "moderately_active", "very_active", "extra_active"]
    ] = None
    goal: Optional[Literal["cut", "maintain", "bulk"]] = None
    dietary_restrictions: Optional[List[str]] = None
    allergies: Optional[List[str]] = None
    budget_weekly: Optional[float] = Field(default=None, gt=0)
    household_size: Optional[int] = Field(default=None, ge=1)
    cooking_skill: Optional[Literal["beginner", "intermediate", "advanced"]] = None
    schedule_json: Optional[Dict[str, Any]] = None


class UserProfileRead(UserProfileBase):
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
