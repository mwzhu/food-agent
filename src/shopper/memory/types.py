from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class EpisodicMemory(BaseModel):
    memory_id: str
    user_id: str
    category: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContextBudget(BaseModel):
    token_budget: int
    tokens_used: int
    fields_included: List[str] = Field(default_factory=list)
    fields_dropped: List[str] = Field(default_factory=list)


class AssembledContext(BaseModel):
    node_name: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    retrieved_memories: List[EpisodicMemory] = Field(default_factory=list)
    budget: ContextBudget
