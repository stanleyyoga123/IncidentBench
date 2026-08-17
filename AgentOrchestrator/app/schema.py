from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AnomalyEventInput(BaseModel):
    event_id: str = Field(min_length=16, max_length=128)
    detected_at: datetime
    resource: str = Field(min_length=1)
    name: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    method: str = Field(min_length=1)
    detail: str = ""
    profile_id: str | None = None
    profile_version: int | None = Field(default=None, ge=1)
    profile_parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def timezone_required(self) -> "AnomalyEventInput":
        if self.detected_at.tzinfo is None:
            raise ValueError("detected_at must be timezone-aware")
        return self


class AnomalyBatchRequest(BaseModel):
    anomalies: list[AnomalyEventInput] = Field(min_length=1, max_length=1000)


class IngestionResponse(BaseModel):
    accepted: int
    duplicates: int
    event_ids: list[str]
    records: list["IngestedEvent"]


class IngestedEvent(BaseModel):
    id: UUID
    event_id: str
    duplicate: bool


class DecisionRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=3, max_length=4000)
    expected_version: int = Field(ge=1)


class RetryRequest(DecisionRequest):
    pass


class Workflow(BaseModel):
    id: UUID
    status: str
    version: int
    rca_job_id: UUID | None = None
    remediation_job_id: UUID | None = None
    decision: str | None = None
    decision_actor: str | None = None
    decision_reason: str | None = None
    error: dict[str, Any] | None = None
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    rca_result: dict[str, Any] | None = None
    remediation_result: dict[str, Any] | None = None
    started_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class WorkflowCollection(BaseModel):
    workflows: list[Workflow]


class DownstreamJob(BaseModel):
    id: UUID
    status: Literal[
        "queued", "running", "succeeded", "failed", "needs_review", "cancelled"
    ]
    version: int = 1
    result: dict[str, Any] | None = None
    raw_output: str | None = None
    error: dict[str, Any] | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
