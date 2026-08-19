from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OrchestratorSettings(BaseModel):
    base_url: str
    token: str
    timeout_seconds: float = 30.0


class ApiSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8083
    submit_token: str


class ClientSettings(BaseModel):
    model: str
    url: str
    token: str = "EMPTY"
    timeout_seconds: int = 120


class WorkerSettings(BaseModel):
    poll_interval_seconds: float = Field(default=2, ge=0.2)
    lease_seconds: int = Field(default=600, ge=60)
    max_attempts: int = Field(default=3, ge=1, le=10)


class Settings(BaseSettings):
    orchestrator: OrchestratorSettings
    api: ApiSettings
    client: ClientSettings
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    model_config = SettingsConfigDict(
        env_nested_delimiter=".", env_file=".env", extra="ignore", frozen=True
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
