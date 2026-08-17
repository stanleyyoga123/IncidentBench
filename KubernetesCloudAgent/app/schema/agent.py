from pydantic import BaseModel, Field


class CallRequest(BaseModel):
    prompt: str = Field(description="User prompt for the LLM agent.")
