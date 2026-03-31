from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from shopper.api.routes import router
from shopper.config import Settings, get_settings
from shopper.db import create_engine, create_session_factory, init_db
from shopper.integrations.browser import BrowserExecutor
from shopper.memory.context import ContextAssembler
from shopper.memory.store import InMemoryEpisodicMemoryStore
from shopper.orchestrator import AppServices, RunOrchestrator
from shopper.services.planning import RECIPE_FIXTURES, RecipeRetriever
from shopper.services.pricing import QuoteAdapter


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
        await init_db(engine)
        services = AppServices(
            memory_store=InMemoryEpisodicMemoryStore(),
            context_assembler=ContextAssembler(),
            recipe_retriever=RecipeRetriever(RECIPE_FIXTURES),
            quote_adapters=[QuoteAdapter("walmart"), QuoteAdapter("mock_club"), QuoteAdapter("mock_organic")],
            browser_executor=BrowserExecutor(),
        )
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.orchestrator = RunOrchestrator(services)
        yield
        await engine.dispose()

    app = FastAPI(title="Shopper", version="0.1.0", lifespan=lifespan)
    app.include_router(router)

    @app.get("/healthz")
    async def healthcheck() -> dict:
        return {"status": "ok", "environment": settings.app_env}

    return app


app = create_app()
