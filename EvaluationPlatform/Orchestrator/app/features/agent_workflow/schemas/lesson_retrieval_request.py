from typing import Any
from pydantic import BaseModel, Field


class LessonRetrievalRequest(BaseModel):
    anomalies: list[dict[str, Any]] = Field(min_length=1, max_length=1000)
