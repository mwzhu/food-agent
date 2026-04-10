from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional, Sequence

from langgraph.graph import END, START, StateGraph

from shopper.supplements.agents.nodes import health_goal_analyzer, store_searcher
from shopper.supplements.agents.nodes.common import DEFAULT_VERIFIED_STORE_DOMAINS
from shopper.supplements.agents.state import DiscoverySubgraphState
from shopper.supplements.tools.shopify_mcp import search_store as default_search_store


SearchStoreFn = Callable[[str, str], Awaitable[list[Any]]]


def build_discovery_subgraph(
    *,
    chat_model: Optional[Any] = None,
    search_store_fn: SearchStoreFn = default_search_store,
    store_domains: Sequence[str] = DEFAULT_VERIFIED_STORE_DOMAINS,
    max_products_per_result: int = 4,
):
    graph = StateGraph(DiscoverySubgraphState)

    async def health_goal_analyzer_node(state: dict[str, Any]) -> dict[str, Any]:
        return await health_goal_analyzer(state, chat_model=chat_model)

    async def store_searcher_node(state: dict[str, Any]) -> dict[str, Any]:
        return await store_searcher(
            state,
            search_store_fn=search_store_fn,
            store_domains=store_domains,
            max_products_per_result=max_products_per_result,
        )

    graph.add_node("health_goal_analyzer", health_goal_analyzer_node)
    graph.add_node("store_searcher", store_searcher_node)
    graph.add_edge(START, "health_goal_analyzer")
    graph.add_edge("health_goal_analyzer", "store_searcher")
    graph.add_edge("store_searcher", END)
    return graph.compile()
