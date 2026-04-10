from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from shopper.config import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_graph(request: Request):
    return request.app.state.graph


def get_run_manager(request: Request):
    return request.app.state.run_manager


def get_supplement_run_manager(request: Request):
    return request.app.state.supplement_run_manager


def get_browser_profile_manager(request: Request):
    return request.app.state.browser_profile_manager


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session
