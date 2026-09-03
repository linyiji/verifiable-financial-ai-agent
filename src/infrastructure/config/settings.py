from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./verifiable_financial.db"
    artifact_root: str = "artifacts"
    workspace_root: str = "workspaces"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()

