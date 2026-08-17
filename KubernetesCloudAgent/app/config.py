from functools import lru_cache
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class KubectlToolSetting(BaseModel):
    path: str
    timeout_seconds: int


class JaegerToolSetting(BaseModel):
    base_url: str
    timeout_seconds: int


class LokiToolSetting(BaseModel):
    base_url: str
    timeout_seconds: int


class PrometheusToolSetting(BaseModel):
    base_url: str
    timeout_seconds: int


class NetworkToolSetting(BaseModel):
    namespace: str = "utility"
    overlay_selector: str = (
        "app.kubernetes.io/name=cloudagent-network-probe,"
        "app.kubernetes.io/component=overlay"
    )
    underlay_selector: str = (
        "app.kubernetes.io/name=cloudagent-network-probe,"
        "app.kubernetes.io/component=underlay"
    )
    timeout_seconds: int = Field(default=30, ge=1)
    max_duration_seconds: int = Field(default=10, ge=1, le=10)
    max_bitrate_mbps: int = Field(default=100, ge=1, le=100)
    max_matrix_nodes: int = Field(default=6, ge=1)


class ToolsSettings(BaseModel):
    kubectl: KubectlToolSetting
    jaeger: JaegerToolSetting
    loki: LokiToolSetting
    prometheus: PrometheusToolSetting
    network: NetworkToolSetting = Field(default_factory=NetworkToolSetting)


class LLMClientParams(BaseModel):
    model: str
    url: str
    token: str
    timeout_seconds: int


class LLMClientSettings(BaseModel):
    type: str
    params: LLMClientParams


class AgentManagerSettings(BaseModel):
    max_orchestration_rounds: int
    memory_path: str = "/app/MEMORY.md"
    memory_max_prompt_chars: int = Field(default=32_000, ge=1_024)


class PostgresSettings(BaseModel):
    dsn: str = "postgresql://postgres:postgres@localhost:5432/postgres"
    poll_interval_seconds: int = 10


class Settings(BaseSettings):
    manager: AgentManagerSettings
    tools: ToolsSettings
    client: LLMClientSettings
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)

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
