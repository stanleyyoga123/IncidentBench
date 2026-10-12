from uuid import UUID
from pydantic import BaseModel


class AttachJobRequest(BaseModel):
    job_id: UUID
