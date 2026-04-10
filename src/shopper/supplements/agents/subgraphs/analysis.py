from __future__ import annotations

from typing import Any, Optional

from langgraph.graph import END, START, StateGraph

from shopper.supplements.agents.nodes import ingredient_comparator, stack_builder
from shopper.supplements.agents.state import AnalysisSubgraphState


def build_analysis_subgraph(
    *,
    chat_model: Optional[Any] = None,
    max_products_per_category: int = 6,
):
    graph = StateGraph(AnalysisSubgraphState)

    async def ingredient_comparator_node(state: dict[str, Any]) -> dict[str, Any]:
        return await ingredient_comparator(
            state,
            chat_model=chat_model,
            max_products_per_category=max_products_per_category,
        )

    async def stack_builder_node(state: dict[str, Any]) -> dict[str, Any]:
        return await stack_builder(state, chat_model=chat_model)

    graph.add_node("ingredient_comparator", ingredient_comparator_node)
    graph.add_node("stack_builder", stack_builder_node)
    graph.add_edge(START, "ingredient_comparator")
    graph.add_edge("ingredient_comparator", "stack_builder")
    graph.add_edge("stack_builder", END)
    return graph.compile()
