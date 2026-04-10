from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shopper.agents import build_planner_graph
from shopper.agents.llm import build_chat_model
from shopper.agents.tools import BrowserCheckoutAgent
from shopper.api import api_router
from shopper.config import Settings, get_settings
from shopper.db import create_engine, create_session_factory, init_db
from shopper.retrieval import EmbeddingService, QdrantRecipeStore, RecipeReranker
from shopper.memory import ContextAssembler, MemoryStore
from shopper.services.browser_profile_manager import BrowserUseCloudProfileManager
from shopper.services.run_manager import RunEventBus, RunManager
from shopper.supplements import models as supplement_models  # noqa: F401
from shopper.supplements.agents import build_supplement_graph
from shopper.supplements.services import SupplementRunEventBus, SupplementRunManager

logger = logging.getLogger(__name__)


def create_app(
    settings: Optional[Settings] = None,
    checkout_agent: Optional[BrowserCheckoutAgent] = None,
    supplement_graph=None,
    supplement_search_store_fn=None,
    supplement_update_cart_fn=None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
        await init_db(engine)

        memory_store = MemoryStore(session_factory=session_factory)
        context_assembler = ContextAssembler(memory_store=memory_store, settings=settings)
        embedding_service = EmbeddingService(settings=settings)
        recipe_store = _build_recipe_store(settings=settings, embedding_service=embedding_service)
        reranker = RecipeReranker(settings=settings)
        chat_model = build_chat_model(settings)
        event_bus = RunEventBus()
        supplement_event_bus = SupplementRunEventBus()
        resolved_checkout_agent = checkout_agent or BrowserCheckoutAgent(settings)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.memory_store = memory_store
        app.state.context_assembler = context_assembler
        app.state.recipe_store = recipe_store
        app.state.embedding_service = embedding_service
        app.state.recipe_reranker = reranker
        app.state.chat_model = chat_model
        app.state.checkout_agent = resolved_checkout_agent
        app.state.browser_profile_manager = BrowserUseCloudProfileManager(settings)
        app.state.graph = build_planner_graph(
            context_assembler=context_assembler,
            memory_store=memory_store,
            recipe_store=recipe_store,
            session_factory=session_factory,
            reranker=reranker,
            chat_model=chat_model,
            settings=settings,
            checkout_agent=resolved_checkout_agent,
        )
        supplement_graph_kwargs = {
            "chat_model": chat_model,
            "settings": settings,
        }
        if supplement_search_store_fn is not None:
            supplement_graph_kwargs["search_store_fn"] = supplement_search_store_fn
        if supplement_update_cart_fn is not None:
            supplement_graph_kwargs["update_cart_fn"] = supplement_update_cart_fn
        app.state.supplement_graph = supplement_graph or build_supplement_graph(**supplement_graph_kwargs)
        app.state.run_manager = RunManager(
            session_factory=session_factory,
            graph=app.state.graph,
            settings=settings,
            event_bus=event_bus,
        )
        app.state.supplement_run_manager = SupplementRunManager(
            session_factory=session_factory,
            graph=app.state.supplement_graph,
            settings=settings,
            event_bus=supplement_event_bus,
        )
        app.state.event_bus = event_bus
        app.state.supplement_event_bus = supplement_event_bus
        yield
        await engine.dispose()

    app = FastAPI(title="Shopper", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.get("/healthz")
    async def healthcheck() -> dict:
        return {"status": "ok", "environment": settings.app_env}

    return app


app = create_app()


def _build_recipe_store(*, settings: Settings, embedding_service: EmbeddingService) -> QdrantRecipeStore:
    corpus_path = Path(settings.recipe_corpus_path)
    try:
        return QdrantRecipeStore(
            corpus_path,
            embedding_service=embedding_service,
            settings=settings,
        )
    except Exception as exc:
        if not settings.qdrant_url:
            raise

        logger.warning(
            "Qdrant startup failed for %s; falling back to in-memory recipe search.",
            settings.qdrant_url,
            exc_info=exc,
        )
        fallback_settings = settings.model_copy(update={"qdrant_url": None})
        return QdrantRecipeStore(
            corpus_path,
            embedding_service=embedding_service,
            settings=fallback_settings,
        )
