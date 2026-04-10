from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
RETIRED_ANTHROPIC_MODEL_ALIASES = frozenset({
    "claude-3-5-sonnet-latest",
    "claude-3-5-sonnet-20240620",
    "claude-3-5-sonnet-20241022",
})


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="SHOPPER_APP_ENV")
    database_url: str = Field(default="sqlite+aiosqlite:///./shopper.db", alias="SHOPPER_DATABASE_URL")
    llm_provider: Literal["anthropic", "openai"] = Field(default="anthropic", alias="SHOPPER_LLM_PROVIDER")
    llm_model: str = Field(default=DEFAULT_ANTHROPIC_MODEL, alias="SHOPPER_LLM_MODEL")
    llm_temperature: float = Field(default=0.2, alias="SHOPPER_LLM_TEMPERATURE", ge=0.0, le=1.0)
    embedding_provider: Literal["openai", "local"] = Field(default="openai", alias="SHOPPER_EMBEDDING_PROVIDER")
    embedding_model: str = Field(default="text-embedding-3-small", alias="SHOPPER_EMBEDDING_MODEL")
    reranker_provider: Literal["cross_encoder", "heuristic"] = Field(
        default="cross_encoder",
        alias="SHOPPER_RERANKER_PROVIDER",
    )
    reranker_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        alias="SHOPPER_RERANKER_MODEL",
    )
    context_tokenizer: str = Field(default="cl100k_base", alias="SHOPPER_CONTEXT_TOKENIZER")
    recipe_corpus_path: str = Field(
        default="data/recipes/phase2_recipe_corpus.json",
        alias="SHOPPER_RECIPE_CORPUS_PATH",
    )
    qdrant_url: Optional[str] = Field(default=None, alias="SHOPPER_QDRANT_URL")
    qdrant_collection: str = Field(default="recipes", alias="SHOPPER_QDRANT_COLLECTION")
    qdrant_api_key: Optional[str] = Field(default=None, alias="SHOPPER_QDRANT_API_KEY")
    qdrant_timeout_s: int = Field(default=10, alias="SHOPPER_QDRANT_TIMEOUT_S", ge=1)
    qdrant_batch_size: int = Field(default=128, alias="SHOPPER_QDRANT_BATCH_SIZE", ge=1)
    qdrant_enable_sparse: bool = Field(default=True, alias="SHOPPER_QDRANT_ENABLE_SPARSE")
    qdrant_dense_vector_name: str = Field(default="dense", alias="SHOPPER_QDRANT_DENSE_VECTOR_NAME")
    qdrant_sparse_vector_name: str = Field(default="sparse", alias="SHOPPER_QDRANT_SPARSE_VECTOR_NAME")
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001",
        alias="SHOPPER_CORS_ORIGINS",
    )
    langsmith_tracing: bool = Field(
        default=False,
        alias="LANGSMITH_TRACING",
        validation_alias=AliasChoices("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"),
    )
    langsmith_project: str = Field(
        default="shopper",
        alias="LANGSMITH_PROJECT",
        validation_alias=AliasChoices("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT"),
    )
    langsmith_api_key: Optional[str] = Field(
        default=None,
        alias="LANGSMITH_API_KEY",
        validation_alias=AliasChoices("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"),
    )
    checkout_artifacts_dir: str = Field(
        default="data/checkout_artifacts",
        alias="SHOPPER_CHECKOUT_ARTIFACTS_DIR",
    )
    checkout_max_order_total_usd: float = Field(
        default=200.0,
        alias="SHOPPER_CHECKOUT_MAX_ORDER_TOTAL_USD",
        ge=0,
    )
    checkout_max_weekly_total_usd: float = Field(
        default=500.0,
        alias="SHOPPER_CHECKOUT_MAX_WEEKLY_TOTAL_USD",
        ge=0,
    )
    checkout_execution_provider: Literal["router", "browser_use", "chatgpt_instacart"] = Field(
        default="router",
        alias="SHOPPER_CHECKOUT_EXECUTION_PROVIDER",
    )
    browser_checkout_headless: bool = Field(default=True, alias="SHOPPER_BROWSER_CHECKOUT_HEADLESS")
    browser_checkout_max_steps: int = Field(default=80, alias="SHOPPER_BROWSER_CHECKOUT_MAX_STEPS", ge=1, le=500)
    browser_checkout_use_cloud: bool = Field(default=False, alias="SHOPPER_BROWSER_CHECKOUT_USE_CLOUD")
    browser_checkout_cloud_profile_id: Optional[str] = Field(
        default=None,
        alias="SHOPPER_BROWSER_CHECKOUT_CLOUD_PROFILE_ID",
    )
    browser_checkout_cloud_proxy_country_code: Optional[str] = Field(
        default=None,
        alias="SHOPPER_BROWSER_CHECKOUT_CLOUD_PROXY_COUNTRY_CODE",
    )
    browser_checkout_cloud_timeout_minutes: Optional[int] = Field(
        default=None,
        alias="SHOPPER_BROWSER_CHECKOUT_CLOUD_TIMEOUT_MINUTES",
        ge=1,
        le=240,
    )
    browser_checkout_captcha_solver: bool = Field(
        default=True,
        alias="SHOPPER_BROWSER_CHECKOUT_CAPTCHA_SOLVER",
    )
    browser_checkout_user_data_dir: Optional[str] = Field(
        default=None,
        alias="SHOPPER_BROWSER_CHECKOUT_USER_DATA_DIR",
    )
    browser_checkout_storage_state_path: Optional[str] = Field(
        default=None,
        alias="SHOPPER_BROWSER_CHECKOUT_STORAGE_STATE_PATH",
    )
    browser_checkout_model_provider: Literal["shopper_default", "anthropic", "openai", "browser_use"] = Field(
        default="shopper_default",
        alias="SHOPPER_BROWSER_CHECKOUT_MODEL_PROVIDER",
    )
    browser_checkout_model: Optional[str] = Field(default=None, alias="SHOPPER_BROWSER_CHECKOUT_MODEL")
    chatgpt_checkout_start_url: str = Field(default="https://chatgpt.com/", alias="SHOPPER_CHATGPT_CHECKOUT_START_URL")
    browser_use_api_key: Optional[str] = Field(default=None, alias="BROWSER_USE_API_KEY")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    usda_api_key: Optional[str] = Field(default=None, alias="USDA_API_KEY")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def resolved_llm_model(self) -> str:
        if self.llm_provider == "anthropic" and self.llm_model in RETIRED_ANTHROPIC_MODEL_ALIASES:
            return DEFAULT_ANTHROPIC_MODEL
        return self.llm_model


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
