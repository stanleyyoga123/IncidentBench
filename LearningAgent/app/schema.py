from datetime import datetime
import hashlib
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


LessonCategory = Literal[
    "investigation", "diagnosis", "remediation", "verification", "guardrail"
]


class LearningJobRequest(BaseModel):
    workflow_id: UUID
    source: dict[str, Any]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def source_hash_must_match(self) -> "LearningJobRequest":
        canonical = json.dumps(self.source, sort_keys=True, separators=(",", ":"))
        if hashlib.sha256(canonical.encode()).hexdigest() != self.source_sha256:
            raise ValueError("source_sha256 does not match source")
        required = {
            "workflow_id", "completion_type", "anomalies", "rca",
            "remediation", "tool_calls",
        }
        missing = required - self.source.keys()
        if missing:
            raise ValueError(f"source is missing required fields: {', '.join(sorted(missing))}")
        if str(self.workflow_id) != str(self.source.get("workflow_id")):
            raise ValueError("source workflow_id does not match workflow_id")
        completion_type = self.source.get("completion_type")
        if completion_type not in {"no_action", "remediated"}:
            raise ValueError("source completion_type must be no_action or remediated")
        if not isinstance(self.source.get("anomalies"), list) or not self.source["anomalies"]:
            raise ValueError("source anomalies must be a non-empty list")
        if not isinstance(self.source.get("rca"), dict):
            raise ValueError("source rca must be an object")
        tool_calls = self.source.get("tool_calls")
        if not isinstance(tool_calls, list) or len(tool_calls) > 100:
            raise ValueError("source tool_calls must contain at most 100 entries")
        remediation = self.source.get("remediation")
        if completion_type == "remediated" and not isinstance(remediation, dict):
            raise ValueError("remediated source requires a remediation result")
        if completion_type == "remediated" and not isinstance(
            remediation.get("result"), dict
        ):
            raise ValueError("remediated source requires structured remediation output")
        if completion_type == "no_action" and remediation is not None:
            raise ValueError("no_action source must not contain remediation data")
        if len(canonical) > 500_000:
            raise ValueError("source exceeds the 500,000-character limit")
        return self


class AtomicLesson(BaseModel):
    category: LessonCategory
    title: str = Field(min_length=3, max_length=200)
    guidance: str = Field(min_length=3, max_length=2000)
    applies_when: list[str] = Field(default_factory=list, max_length=10)
    avoid: list[str] = Field(default_factory=list, max_length=10)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)
    resource: str | None = Field(default=None, max_length=200)
    name: str | None = Field(default=None, max_length=300)
    metric: str | None = Field(default=None, max_length=300)
    tags: list[str] = Field(default_factory=list, max_length=20)
    confidence: float = Field(ge=0, le=1)


class LearningResult(BaseModel):
    summary: str = Field(min_length=1, max_length=4000)
    lessons: list[AtomicLesson] = Field(default_factory=list, max_length=20)


class LearningJob(BaseModel):
    id: UUID
    workflow_id: UUID
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    version: int
    request: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    raw_output: str | None = None
    error: dict[str, Any] | None = None
    attempts: int = 0
    created_at: datetime
    updated_at: datetime
