from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="SHOPPER_APP_ENV")
    database_url: str = Field(
        default="sqlite+aiosqlite:///./shopper.db",
        alias="SHOPPER_DATABASE_URL",
    )
    langsmith_tracing: bool = Field(default=False, alias="SHOPPER_LANGSMITH_TRACING")
    langsmith_project: str = Field(default="shopper", alias="SHOPPER_LANGSMITH_PROJECT")
    qdrant_url: str = Field(default="http://localhost:6333", alias="SHOPPER_QDRANT_URL")
    memory_backend: str = Field(default="inmemory", alias="SHOPPER_MEMORY_BACKEND")
    approval_required: bool = Field(default=True, alias="SHOPPER_APPROVAL_REQUIRED")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


def get_settings() -> Settings:
    return Settings()

