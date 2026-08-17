from functools import lru_cache

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CooldownMechanismSettings(BaseModel):
    time: float = 60


class MetadataCollectorSettings(BaseModel):
    namespaces: list[str]
    excluded_nodes: list[str] = Field(
        default_factory=lambda: ["tools-node", "misc-node-1"]
    )


class MetricsCollectorSettings(BaseModel):
    base_url: str
    timeout: int
    history_minutes: int = 65
    query_step_seconds: int = 30
    max_concurrency: int = 4

    @model_validator(mode="after")
    def validate_history_window(self) -> "MetricsCollectorSettings":
        if self.history_minutes <= 0:
            raise ValueError("history_minutes must be positive")
        if self.query_step_seconds <= 0:
            raise ValueError("query_step_seconds must be positive")
        if self.max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")

        sample_count = (self.history_minutes * 60) // self.query_step_seconds + 1
        if sample_count < 123:
            raise ValueError(
                "Prometheus history window must provide at least 123 samples "
                "for the 120-point detector lookback and 3-point tail"
            )
        return self


class DetectorSettings(BaseModel):
    interval_seconds: float = 30.0
    cooldown_seconds: float = 120.0
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8080, ge=1, le=65535)
    profile_api_token: str | None = None


class CollectorSettings(BaseModel):
    metadata: MetadataCollectorSettings
    metrics: MetricsCollectorSettings


class OrchestratorSettings(BaseModel):
    base_url: str = "http://agent-orchestrator:8080"
    ingestion_token: str
    timeout_seconds: float = Field(default=10, gt=0)
    max_attempts: int = Field(default=3, ge=1, le=10)


class Settings(BaseSettings):
    collector: CollectorSettings
    detector: DetectorSettings
    orchestrator: OrchestratorSettings

    model_config = SettingsConfigDict(
        env_nested_delimiter=".",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


SETTINGS = get_settings()
