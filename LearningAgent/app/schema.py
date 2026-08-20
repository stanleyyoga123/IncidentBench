from datetime import datetime
import hashlib
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


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


CONFIDENCE_LABELS = {
    "very high": 0.9,
    "very-high": 0.9,
    "high": 0.8,
    "medium-high": 0.7,
    "medium high": 0.7,
    "moderately high": 0.7,
    "moderate-high": 0.7,
    "medium": 0.5,
    "moderate": 0.5,
    "medium-low": 0.3,
    "medium low": 0.3,
    "moderately low": 0.3,
    "moderate-low": 0.3,
    "low": 0.2,
    "very low": 0.1,
    "very-low": 0.1,
}


def _as_string_list(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, list):
        items = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                items.append(text)
        return items
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return value


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

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("applies_when", "avoid", "evidence_refs", "tags", mode="before")
    @classmethod
    def coerce_string_lists(cls, value: Any) -> Any:
        return _as_string_list(value)

    @field_validator("resource", "name", "metric", mode="before")
    @classmethod
    def blank_scope_to_none(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, value: Any) -> Any:
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (int, float)):
            number = float(value)
            if 1 < number <= 100:
                return number / 100.0
            return number
        if isinstance(value, str):
            text = value.strip().lower().rstrip("%")
            if text in CONFIDENCE_LABELS:
                return CONFIDENCE_LABELS[text]
            try:
                number = float(text)
            except ValueError:
                return value
            if 1 < number <= 100:
                return number / 100.0
            return number
        return value


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
