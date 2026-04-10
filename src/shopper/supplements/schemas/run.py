from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shopper.supplements.schemas.health import HealthProfile, SupplementNeed
from shopper.supplements.schemas.product import CategoryDiscoveryResult, ProductComparison
from shopper.supplements.schemas.recommendation import StoreCart, SupplementStack


SupplementRunLifecycleStatus = Literal[
    "pending",
    "running",
    "awaiting_approval",
    "completed",
    "failed",
]
SupplementPhaseName = Literal["memory", "discovery", "analysis", "checkout"]
SupplementPhaseStatus = Literal["pending", "running", "completed", "locked", "failed"]
SupplementRunEventType = Literal[
    "phase_started",
    "phase_completed",
    "node_entered",
    "node_completed",
    "approval_requested",
    "approval_resolved",
    "run_completed",
    "error",
]
SupplementCriticDecision = Literal["passed", "manual_review_needed", "failed"]
SupplementCriticConcern = Literal["safety", "goal_alignment", "value"]


class SupplementCriticFinding(BaseModel):
    concern: SupplementCriticConcern
    severity: Literal["issue", "warning"]
    message: str

    model_config = ConfigDict(str_strip_whitespace=True)


class SupplementCriticVerdict(BaseModel):
    decision: SupplementCriticDecision = "passed"
    summary: str = ""
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    findings: list[SupplementCriticFinding] = Field(default_factory=list)
    manual_review_reason: Optional[str] = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @property
    def passed(self) -> bool:
        return self.decision == "passed"


class SupplementRunEvent(BaseModel):
    event_id: str
    run_id: str
    event_type: SupplementRunEventType
    message: str
    phase: Optional[SupplementPhaseName] = None
    node_name: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(str_strip_whitespace=True)


class SupplementPhaseStatuses(BaseModel):
    memory: SupplementPhaseStatus = "pending"
    discovery: SupplementPhaseStatus = "locked"
    analysis: SupplementPhaseStatus = "locked"
    checkout: SupplementPhaseStatus = "locked"


class SupplementTraceMetadata(BaseModel):
    kind: Optional[str] = None
    project: Optional[str] = None
    trace_id: Optional[str] = None
    source: Optional[str] = None


class SupplementStateSnapshot(BaseModel):
    run_id: str
    user_id: str
    health_profile: HealthProfile
    identified_needs: list[SupplementNeed] = Field(default_factory=list)
    discovery_results: list[CategoryDiscoveryResult] = Field(default_factory=list)
    product_comparisons: list[ProductComparison] = Field(default_factory=list)
    recommended_stack: Optional[SupplementStack] = None
    critic_verdict: Optional[SupplementCriticVerdict] = None
    store_carts: list[StoreCart] = Field(default_factory=list)
    approved_store_domains: list[str] = Field(default_factory=list)
    status: SupplementRunLifecycleStatus = "pending"
    current_node: str = "created"
    current_phase: Optional[SupplementPhaseName] = None
    phase_statuses: SupplementPhaseStatuses = Field(default_factory=SupplementPhaseStatuses)
    replan_count: int = 0
    latest_error: Optional[str] = None
    trace_metadata: SupplementTraceMetadata = Field(default_factory=SupplementTraceMetadata)

    model_config = ConfigDict(str_strip_whitespace=True)

    @classmethod
    def starting(
        cls,
        *,
        run_id: str,
        user_id: str,
        health_profile: Union[HealthProfile, Dict[str, Any]],
    ) -> "SupplementStateSnapshot":
        return cls(
            run_id=run_id,
            user_id=user_id,
            health_profile=health_profile,
            status="running",
            current_phase="memory",
            phase_statuses=SupplementPhaseStatuses(memory="running"),
        )

    def as_failed(self, message: str) -> "SupplementStateSnapshot":
        phase = self.current_phase or "memory"
        phase_statuses = self.phase_statuses.model_copy(deep=True)
        if phase == "memory":
            phase_statuses.memory = "failed"
        elif phase == "discovery":
            phase_statuses.memory = "completed"
            phase_statuses.discovery = "failed"
        elif phase == "analysis":
            phase_statuses.memory = "completed"
            phase_statuses.discovery = "completed"
            phase_statuses.analysis = "failed"
        else:
            phase_statuses.memory = "completed"
            phase_statuses.discovery = "completed"
            phase_statuses.analysis = "completed"
            phase_statuses.checkout = "failed"

        return self.model_copy(
            update={
                "status": "failed",
                "latest_error": message,
                "current_phase": phase,
                "current_node": "error",
                "phase_statuses": phase_statuses,
            }
        )


def _normalize_store_domains(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError("value must be a list of strings")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if item is None:
            continue
        domain = str(item).strip().lower()
        if not domain or domain in seen:
            continue
        normalized.append(domain)
        seen.add(domain)
    return normalized


class SupplementRunCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    health_profile: HealthProfile

    model_config = ConfigDict(str_strip_whitespace=True)


class SupplementRunApproveRequest(BaseModel):
    approved_store_domains: list[str] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("approved_store_domains", mode="before")
    @classmethod
    def _normalize_domains(cls, value: Any) -> list[str]:
        return _normalize_store_domains(value)


class SupplementRunRead(BaseModel):
    run_id: str
    user_id: str
    status: SupplementRunLifecycleStatus
    state_snapshot: SupplementStateSnapshot
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
