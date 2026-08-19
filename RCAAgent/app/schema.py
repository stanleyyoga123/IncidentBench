from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class HistoricalLesson(BaseModel):
    id: UUID
    category: Literal[
        "investigation", "diagnosis", "remediation", "verification", "guardrail"
    ]
    title: str
    guidance: str
    applies_when: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    resource: str | None = None
    name: str | None = None
    metric: str | None = None
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class RCAJobRequest(BaseModel):
    workflow_id: UUID | None = None
    anomalies: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    caller_context: str | None = Field(default=None, max_length=8000)
    historical_lessons: list[HistoricalLesson] = Field(
        default_factory=list, max_length=40
    )


class RemediationPlan(BaseModel):
    action: str = ""
    targets: list[str] = Field(default_factory=list)
    expected_benefit: str = ""
    verification: list[str] = Field(default_factory=list)
    rollback: list[str] = Field(default_factory=list)
    guardrails: list[str] = Field(default_factory=list)


class RCAResult(BaseModel):
    remediation_required: bool
    incident_state: Literal[
        "active", "recovered", "intermittent", "preventive risk", "unconfirmed"
    ] = "unconfirmed"
    summary: str
    failed_investigations: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    impact_scope: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    remediation_plan: RemediationPlan = Field(default_factory=RemediationPlan)


class RCAJob(BaseModel):
    id: UUID
    workflow_id: UUID | None = None
    status: Literal["queued", "running", "succeeded", "failed", "needs_review", "cancelled"]
    version: int
    request: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    raw_output: str | None = None
    error: dict[str, Any] | None = None
    attempts: int = 0
    created_at: datetime
    updated_at: datetime
