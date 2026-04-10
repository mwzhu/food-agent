from __future__ import annotations

from typing import Any

__all__ = ["build_planner_graph", "invoke_planner_graph"]


def build_planner_graph(*args: Any, **kwargs: Any):
    from shopper.agents.graph import build_planner_graph as _build_planner_graph

    return _build_planner_graph(*args, **kwargs)


async def invoke_planner_graph(*args: Any, **kwargs: Any):
    from shopper.agents.graph import invoke_planner_graph as _invoke_planner_graph

    return await _invoke_planner_graph(*args, **kwargs)
