from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shopper.agents import build_planner_graph
from shopper.api import api_router
from shopper.config import Settings, get_settings
from shopper.db import create_engine, create_session_factory, init_db
from shopper.memory import ContextAssembler, MemoryStore


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
        await init_db(engine)

        memory_store = MemoryStore()
        context_assembler = ContextAssembler(memory_store=memory_store)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.memory_store = memory_store
        app.state.context_assembler = context_assembler
        app.state.graph = build_planner_graph(context_assembler=context_assembler)
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
