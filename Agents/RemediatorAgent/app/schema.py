from datetime import datetime
import hashlib
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class Approval(BaseModel):
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=3)
    workflow_version: int = Field(ge=1)


class RemediationJobRequest(BaseModel):
    workflow_id: UUID | None = None
    rca_job_id: UUID
    rca_result: dict[str, Any]
    rca_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval: Approval

    @model_validator(mode="after")
    def remediation_must_be_required(self):
        if self.rca_result.get("remediation_required") is not True:
            raise ValueError("RCA result does not require remediation")
        canonical = json.dumps(self.rca_result, sort_keys=True, separators=(",", ":"))
        if hashlib.sha256(canonical.encode()).hexdigest() != self.rca_result_sha256:
            raise ValueError("rca_result_sha256 does not match rca_result")
        return self


class RemediationResult(BaseModel):
    summary: str
    changes: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


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
