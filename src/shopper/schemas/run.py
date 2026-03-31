from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

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


class RunTraceRead(BaseModel):
    run_id: str
    kind: Optional[str] = None
    project: Optional[str] = None
    trace_id: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
