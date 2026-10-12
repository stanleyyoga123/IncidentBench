from typing import Any

from pydantic import BaseModel

from features.agent_workflow.schema import Workflow


class PendingClaimResponse(BaseModel):
    workflow: Workflow
    anomalies: list[dict[str, Any]]
