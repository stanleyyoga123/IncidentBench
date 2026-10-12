from typing import Literal
from features.agent_workflow.schema import Workflow
from pydantic import BaseModel, Field


class WorkflowDecisionRequest(BaseModel):
    decision: Literal["approved", "declined"]
    actor: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=3, max_length=4000)
    expected_version: int = Field(ge=1)
