from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from shopper.schemas.common import PlannerStateSnapshot, RunLifecycleStatus
from shopper.schemas.user import UserProfileBase


class RunCreateRequest(BaseModel):
    user_id: str
    profile: UserProfileBase


class RunRead(BaseModel):
    run_id: str
    user_id: str
    status: RunLifecycleStatus
    state_snapshot: PlannerStateSnapshot
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
