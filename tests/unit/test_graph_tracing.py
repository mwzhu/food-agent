from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import langsmith

from shopper.agents.graph import invoke_planner_graph
from shopper.config import Settings


class FakeGraph:
    def __init__(self, result: Dict[str, Any]) -> None:
        self._result = result
        self.received_config: Optional[Dict[str, Any]] = None
        self.received_state: Optional[Dict[str, Any]] = None

    async def ainvoke(
        self,
        state: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.received_state = state
        self.received_config = config
        return dict(self._result)


class FakeTraceContext:
    def __init__(self, captured: Dict[str, Any], **kwargs: Any) -> None:
        self._captured = captured
        self._kwargs = kwargs

    def __enter__(self) -> None:
        self._captured["trace_context"] = self._kwargs

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeRootRun:
    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id
        self.ended_outputs: Optional[Dict[str, Any]] = None

    async def __aenter__(self) -> "FakeRootRun":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def end(self, outputs: Dict[str, Any]) -> None:
        self.ended_outputs = outputs


def test_invoke_planner_graph_uses_langsmith_trace_context(monkeypatch) -> None:
    captured: Dict[str, Any] = {}
    graph = FakeGraph(
        {
            "status": "completed",
            "current_phase": "planning",
            "current_node": "critic",
            "selected_meals": [{"recipe_id": "meal-1"}],
            "critic_verdict": {"passed": True},
            "context_metadata": [],
        }
    )

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            captured["client_api_key"] = api_key

    def fake_tracing_context(**kwargs: Any) -> FakeTraceContext:
        return FakeTraceContext(captured, **kwargs)

    def fake_trace(**kwargs: Any) -> FakeRootRun:
        captured["trace_kwargs"] = kwargs
        root_run = FakeRootRun(trace_id="remote-trace-id")
        captured["root_run"] = root_run
        return root_run

    monkeypatch.setattr(langsmith, "Client", FakeClient)
    monkeypatch.setattr(langsmith, "tracing_context", fake_tracing_context)
    monkeypatch.setattr(langsmith, "trace", fake_trace)

    settings = Settings(
        SHOPPER_APP_ENV="test",
        LANGSMITH_TRACING=True,
        LANGSMITH_PROJECT="shopper-observability",
        LANGSMITH_API_KEY="test-key",
    )

    result = asyncio.run(
        invoke_planner_graph(
            graph=graph,
            state={"run_id": "run-123", "user_id": "user-456"},
            settings=settings,
            source="api",
        )
    )

    assert result["trace_metadata"] == {
        "kind": "remote",
        "project": "shopper-observability",
        "trace_id": "remote-trace-id",
        "source": "api",
    }
    assert graph.received_config == {
        "run_name": "api:planner_graph",
        "tags": ["shopper", "api"],
        "metadata": {
            "phase": "phase5",
            "source": "api",
            "shopper_run_id": "run-123",
            "user_id": "user-456",
        },
    }
    assert graph.received_state is not None
    assert graph.received_state["trace_metadata"]["trace_id"] == "remote-trace-id"
    assert captured["client_api_key"] == "test-key"
    assert captured["trace_context"]["enabled"] is True
    assert captured["trace_context"]["project_name"] == "shopper-observability"
    assert captured["trace_context"]["tags"] == ["shopper", "api"]
    assert isinstance(captured["trace_context"]["client"], FakeClient)
    assert captured["trace_context"]["metadata"] == {
        "phase": "phase5",
        "source": "api",
        "shopper_run_id": "run-123",
        "user_id": "user-456",
    }
    assert captured["trace_kwargs"] == {
        "name": "api:planner_run",
        "run_type": "chain",
        "inputs": {
            "run_id": "run-123",
            "user_id": "user-456",
            "source": "api",
        },
    }
    assert captured["root_run"].ended_outputs == {
        "status": "completed",
        "current_phase": "planning",
        "current_node": "critic",
        "selected_meal_count": 1,
        "grocery_item_count": 0,
        "critic_passed": True,
    }


def test_settings_accept_legacy_langchain_tracing_aliases() -> None:
    settings = Settings(
        SHOPPER_APP_ENV="test",
        LANGCHAIN_TRACING_V2=True,
        LANGCHAIN_PROJECT="legacy-project",
        LANGCHAIN_API_KEY="legacy-key",
    )

    assert settings.langsmith_tracing is True
    assert settings.langsmith_project == "legacy-project"
    assert settings.langsmith_api_key == "legacy-key"
