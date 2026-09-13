from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    dsn: str


class ApiSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = Field(default=8080, ge=1, le=65535)
    ingestion_token: str
    control_token: str
    store_token: str


class ServiceClientSettings(BaseModel):
    base_url: str
    token: str
    timeout_seconds: float = 30.0


class SchedulerSettings(BaseModel):
    intake_interval_seconds: float = Field(default=60, ge=1)
    reconcile_interval_seconds: float = Field(default=5, ge=1)
    batch_size: int = Field(default=100, ge=1, le=1000)


class Settings(BaseSettings):
    database: DatabaseSettings
    api: ApiSettings
    rca: ServiceClientSettings
    remediator: ServiceClientSettings
    learning: ServiceClientSettings
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)

    model_config = SettingsConfigDict(
        env_nested_delimiter=".", env_file=".env", extra="ignore", frozen=True
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
