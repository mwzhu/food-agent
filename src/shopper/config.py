from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="SHOPPER_APP_ENV")
    database_url: str = Field(default="sqlite+aiosqlite:///./shopper.db", alias="SHOPPER_DATABASE_URL")
    langchain_project: str = Field(default="shopper-phase1", alias="LANGCHAIN_PROJECT")
    enable_remote_langsmith: bool = Field(default=False, alias="SHOPPER_ENABLE_REMOTE_LANGSMITH")
    langchain_api_key: Optional[str] = Field(default=None, alias="LANGCHAIN_API_KEY")
    usda_api_key: Optional[str] = Field(default=None, alias="USDA_API_KEY")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
