from typing import Any
from typing import Literal
from pydantic import BaseModel


class RCAStateRequest(BaseModel):
    status: Literal["queued", "running", "succeeded", "failed", "needs_review", "cancelled"]
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
