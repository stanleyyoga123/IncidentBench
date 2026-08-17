from typing import Any
from datetime import datetime

from pydantic import BaseModel, Field
from schema.storage import Metadata


class Detection(BaseModel):
    metadata: Metadata
    method: str
    detail: str
    is_anomaly: bool
    detected_at: datetime | None = None
    profile_id: str | None = None
    profile_version: int | None = None
    profile_parameters: dict[str, Any] = Field(default_factory=dict)
