from __future__ import annotations

import asyncio
from pathlib import Path

from shopper.config import Settings
from shopper.db import create_engine, create_session_factory, init_db
from shopper.memory import MemoryStore


def test_memory_store_persists_when_backed_by_database(tmp_path: Path):
    asyncio.run(_exercise_memory_store(tmp_path))


async def _exercise_memory_store(tmp_path: Path) -> None:
    settings = Settings(
        SHOPPER_DATABASE_URL="sqlite+aiosqlite:///{path}".format(path=tmp_path / "memory.db"),
        SHOPPER_APP_ENV="test",
        LANGSMITH_TRACING=False,
    )
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    await init_db(engine)

    writer = MemoryStore(session_factory=session_factory)
    memory_id = await writer.save_memory(
        user_id="alex",
        category="meal_feedback",
        content="Loved the mediterranean salmon bowl.",
        metadata={"cuisine": "mediterranean", "meal_type": "dinner"},
    )

    reader = MemoryStore(session_factory=session_factory)
    recalled = await reader.recall("alex", "salmon dinner", top_k=5)
    summary = await reader.summarize_preferences("alex")

    assert recalled
    assert recalled[0].memory_id == memory_id
    assert "mediterranean" in summary.preferred_cuisines

    await engine.dispose()
