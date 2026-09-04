from functools import lru_cache

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    url: str


class FMPSettings(BaseModel):
    api_key: SecretStr | None
    base_url: str

    @property
    def enabled(self) -> bool:
        return self.api_key is not None and bool(self.api_key.get_secret_value())


class LLMSettings(BaseModel):
    provider: str
    api_key: SecretStr | None
    base_url: str
    primary_model: str
    fallback_model: str

    @property
    def enabled(self) -> bool:
        return self.api_key is not None and bool(self.api_key.get_secret_value())


class LangfuseSettings(BaseModel):
    public_key: SecretStr | None
    secret_key: SecretStr | None
    base_url: str | None

    @property
    def enabled(self) -> bool:
        values = (self.public_key, self.secret_key)
        return all(value is not None and bool(value.get_secret_value()) for value in values)


class RuntimeSettings(BaseModel):
    artifact_root: str
    workspace_root: str


class Settings(BaseSettings):
    """Single process-wide source for configuration and secrets.

    Secrets intentionally use ``SecretStr`` so model representations and accidental
    logging stay redacted. Adapters receive the relevant typed subsection through
    dependency injection; they must not read environment files themselves.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./verifiable_financial.db"
    artifact_root: str = "artifacts"
    workspace_root: str = "workspaces"
    fmp_api_key: SecretStr | None = None
    fmp_base_url: str = "https://financialmodelingprep.com"
    llm_provider: str = "teamorouter"
    teamorouter_api_key: SecretStr | None = None
    teamorouter_base_url: str = "https://api.teamorouter.com/v1"
    teamorouter_model: str = "gpt-5.6-sol"
    teamorouter_fallback_model: str = "gpt-5.6-luna"
    mimo_api_key: SecretStr | None = None
    mimo_base_url: str = "https://api.xiaomimimo.com/v1"
    mimo_data_model: str = "mimo-v2.5"
    mimo_chat_model: str = "mimo-v2.5"
    planner_preferred_provider: str = "mimo"
    planner_fallback_providers: str = "teamorouter"
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str | None = None

    @property
    def database(self) -> DatabaseSettings:
        return DatabaseSettings(url=self.database_url)

    @property
    def fmp(self) -> FMPSettings:
        return FMPSettings(api_key=self.fmp_api_key, base_url=self.fmp_base_url)

    @property
    def llm(self) -> LLMSettings:
        return LLMSettings(
            provider=self.llm_provider,
            api_key=self.teamorouter_api_key,
            base_url=self.teamorouter_base_url,
            primary_model=self.teamorouter_model,
            fallback_model=self.teamorouter_fallback_model,
        )

    @property
    def mimo(self) -> LLMSettings:
        return LLMSettings(
            provider="mimo",
            api_key=self.mimo_api_key,
            base_url=self.mimo_base_url,
            primary_model=self.mimo_chat_model,
            fallback_model=self.mimo_chat_model,
        )

    @property
    def planner_provider_order(self) -> tuple[str, ...]:
        values = (
            self.planner_preferred_provider,
            *self.planner_fallback_providers.split(","),
        )
        normalized = tuple(
            dict.fromkeys(value.strip().lower() for value in values if value.strip())
        )
        if not normalized or not set(normalized).issubset({"mimo", "teamorouter"}):
            raise ValueError("planner provider policy contains an unsupported provider")
        return normalized

    @property
    def langfuse(self) -> LangfuseSettings:
        return LangfuseSettings(
            public_key=self.langfuse_public_key,
            secret_key=self.langfuse_secret_key,
            base_url=self.langfuse_base_url,
        )

    @property
    def runtime(self) -> RuntimeSettings:
        return RuntimeSettings(
            artifact_root=self.artifact_root,
            workspace_root=self.workspace_root,
        )

    def safe_summary(self) -> dict[str, str | bool]:
        """Return only non-secret values and credential presence flags."""

        return {
            "fmp_api_key_is_set": self.fmp.enabled,
            "teamorouter_api_key_is_set": self.llm.enabled,
            "llm_provider": self.llm.provider,
            "teamorouter_base_url": self.llm.base_url,
            "teamorouter_model": self.llm.primary_model,
            "teamorouter_fallback_model": self.llm.fallback_model,
            "mimo_api_key_is_set": self.mimo.enabled,
            "mimo_base_url": self.mimo.base_url,
            "mimo_chat_model": self.mimo.primary_model,
            "mimo_data_model": self.mimo_data_model,
            "planner_provider_order": self.planner_provider_order,
            "langfuse_credentials_are_set": self.langfuse.enabled,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
