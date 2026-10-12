from pydantic import BaseModel, Field


class PendingClaimRequest(BaseModel):
    limit: int = Field(ge=1, le=1000)
