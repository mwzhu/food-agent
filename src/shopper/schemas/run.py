from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict

from shopper.schemas.user import UserProfileBase


class RunCreateRequest(BaseModel):
    user_id: str
    profile: UserProfileBase


class RunRead(BaseModel):
    run_id: str
    user_id: str
    status: Literal["running", "completed"]
    state_snapshot: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
