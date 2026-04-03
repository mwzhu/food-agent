from __future__ import annotations

from typing import Any, Optional, Type

from langchain_core.language_models.chat_models import BaseChatModel

from shopper.config import Settings


def build_chat_model(settings: Settings) -> Optional[BaseChatModel]:
    if settings.app_env == "test":
        return None

    provider = settings.llm_provider
    if provider == "openai":
        if not settings.openai_api_key:
            return None
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            return None
        return ChatOpenAI(
            model=settings.resolved_llm_model,
            temperature=settings.llm_temperature,
            api_key=settings.openai_api_key,
        )

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            return None
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            return None
        return ChatAnthropic(
            model=settings.resolved_llm_model,
            temperature=settings.llm_temperature,
            api_key=settings.anthropic_api_key,
        )

    return None


async def invoke_structured(
    chat_model: Optional[Any],
    schema: Type[Any],
    messages: list[Any],
) -> Optional[Any]:
    if chat_model is None:
        return None

    binder = getattr(chat_model, "with_structured_output", None)
    if binder is None:
        return None

    structured_model = binder(schema)
    return await structured_model.ainvoke(messages)
