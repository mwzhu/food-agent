from __future__ import annotations

from fastapi.testclient import TestClient

from shopper.config import Settings
from shopper.main import create_app


def test_app_startup_falls_back_when_qdrant_is_unavailable(tmp_path):
    settings = Settings(
        SHOPPER_DATABASE_URL="sqlite+aiosqlite:///{path}".format(path=tmp_path / "startup-fallback.db"),
        SHOPPER_APP_ENV="test",
        SHOPPER_QDRANT_URL="http://127.0.0.1:1",
        SHOPPER_QDRANT_TIMEOUT_S=1,
        LANGSMITH_TRACING=False,
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/healthz")

        assert response.status_code == 200
        assert client.app.state.recipe_store.uses_qdrant is False
