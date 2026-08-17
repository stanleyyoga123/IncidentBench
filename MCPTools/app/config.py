from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8090
    profile: Literal["investigation", "remediation"] = "investigation"
    token: str


class EndpointSettings(BaseModel):
    base_url: str
    timeout_seconds: int = 20


class KubectlSettings(BaseModel):
    path: str = "kubectl"
    timeout_seconds: int = 30


class NetworkSettings(BaseModel):
    namespace: str = "utility"
    overlay_selector: str = "app.kubernetes.io/name=mcp-tools-network-probe,app.kubernetes.io/component=overlay"
    underlay_selector: str = "app.kubernetes.io/name=mcp-tools-network-probe,app.kubernetes.io/component=underlay"
    timeout_seconds: int = 30
    max_duration_seconds: int = 10
    max_bitrate_mbps: int = 100
    max_matrix_nodes: int = 6


class ToolsSettings(BaseModel):
    kubectl: KubectlSettings
    prometheus: EndpointSettings
    loki: EndpointSettings
    jaeger: EndpointSettings
    network: NetworkSettings = Field(default_factory=NetworkSettings)
    remediation_root: str = "/var/lib/mcp-tools/remediation"


class Settings(BaseSettings):
    server: ServerSettings
    tools: ToolsSettings
    model_config = SettingsConfigDict(
        env_nested_delimiter=".", env_file=".env", extra="ignore", frozen=True
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
