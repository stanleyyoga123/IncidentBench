from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    dsn: str


class ApiSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = Field(default=8080, ge=1, le=65535)
    control_token: str
    store_token: str


class Settings(BaseSettings):
    database: DatabaseSettings
    api: ApiSettings

    model_config = SettingsConfigDict(
        env_nested_delimiter=".", env_file=".env", extra="ignore", frozen=True
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
