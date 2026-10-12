from typing import Any
from pydantic import BaseModel


class SubmissionFailureRequest(BaseModel):
    error: dict[str, Any]
