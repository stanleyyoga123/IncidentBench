from functools import lru_cache
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    dsn: str


class ApiSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8082
    submit_token: str


class MCPSettings(BaseModel):
    url: str
    token: str


class ClientSettings(BaseModel):
    model: str
    url: str
    token: str = "EMPTY"
    timeout_seconds: int = 300


class WorkerSettings(BaseModel):
    poll_interval_seconds: float = Field(default=2, ge=0.2)
    lease_seconds: int = Field(default=1800, ge=60)


class ManagerSettings(BaseModel):
    max_rounds: int = Field(default=50, ge=1, le=100)


class Settings(BaseSettings):
    database: DatabaseSettings
    api: ApiSettings
    mcp: MCPSettings
    client: ClientSettings
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    manager: ManagerSettings = Field(default_factory=ManagerSettings)
    model_config = SettingsConfigDict(
        env_nested_delimiter=".", env_file=".env", extra="ignore", frozen=True
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


SETTINGS = get_settings()
