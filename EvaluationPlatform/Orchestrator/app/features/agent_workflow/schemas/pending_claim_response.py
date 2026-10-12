from typing import Any
from features.agent_workflow.schema import Workflow
from pydantic import BaseModel


class PendingClaimResponse(BaseModel):
    workflow: Workflow
    anomalies: list[dict[str, Any]]
