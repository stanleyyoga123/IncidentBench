from datetime import datetime, timezone
import hashlib
import json
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


class RCAJobCreateRequest(BaseModel):
    workflow_id: UUID | None = None
    anomalies: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    caller_context: str | None = Field(default=None, max_length=8000)


class RemediationApproval(BaseModel):
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=3)
    workflow_version: int = Field(ge=1)


class RemediationJobCreateRequest(BaseModel):
    workflow_id: UUID | None = None
    rca_job_id: UUID
    rca_result: dict[str, Any]
    rca_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval: RemediationApproval

    @model_validator(mode="after")
    def remediation_must_be_required(self) -> "RemediationJobCreateRequest":
        if self.rca_result.get("remediation_required") is not True:
            raise ValueError("RCA result does not require remediation")
        canonical = json.dumps(self.rca_result, sort_keys=True, separators=(",", ":"))
        if hashlib.sha256(canonical.encode()).hexdigest() != self.rca_result_sha256:
            raise ValueError("rca_result_sha256 does not match rca_result")
        return self


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


class RemediationJob(BaseModel):
    id: UUID
    workflow_id: UUID | None = None
    rca_job_id: UUID
    status: Literal["queued", "running", "succeeded", "failed", "needs_review", "cancelled"]
    version: int
    request: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    raw_output: str | None = None
    error: dict[str, Any] | None = None
    attempts: int = 0
    created_at: datetime
    updated_at: datetime


class ExecutionClaimRequest(BaseModel):
    service: Literal["rca", "remediation"]
    owner: str = Field(min_length=1, max_length=400)
    lease_seconds: int = Field(ge=60)
    max_attempts: int = Field(default=3, ge=1, le=10)


class ExecutionRenewRequest(BaseModel):
    service: Literal["rca", "remediation"]
    job_id: UUID
    owner: str = Field(min_length=1, max_length=400)
    lease_seconds: int = Field(ge=60)


class RCAFinishRequest(BaseModel):
    outcome: Literal["succeeded", "failed"]
    result: dict[str, Any] | None = None
    raw_output: str | None = None
    error: dict[str, Any] | None = None
    max_attempts: int = Field(default=3, ge=1, le=10)


class RemediationFinishRequest(BaseModel):
    status: Literal["succeeded", "needs_review"]
    result: dict[str, Any] | None = None
    raw_output: str | None = None
    error: dict[str, Any] | None = None


class ToolCallRequest(BaseModel):
    tool_name: str = Field(min_length=1, max_length=200)
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None


class ArtifactUpsertRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    content: str = ""


class RenewResponse(BaseModel):
    renewed: bool


class ArtifactListResponse(BaseModel):
    filenames: list[str]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
