from typing import Any
from typing import Literal
from pydantic import BaseModel


class JobStateRequest(BaseModel):
    status: Literal["queued", "running", "succeeded", "failed", "needs_review", "cancelled"]
    error: dict[str, Any] | None = None
