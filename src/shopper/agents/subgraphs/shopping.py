from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from shopper.agents.nodes import GroceryBuilderNode, PriceOptimizerNode
from shopper.agents.state import ShoppingSubgraphState


def build_shopping_subgraph(
    get_fridge_contents_tool,
    context_assembler=None,
    chat_model=None,
):
    graph = StateGraph(ShoppingSubgraphState)
    graph.add_node(
        "grocery_builder",
        GroceryBuilderNode(
            get_fridge_contents_tool=get_fridge_contents_tool,
        ),
    )
    graph.add_node(
        "price_optimizer",
        PriceOptimizerNode(
            context_assembler=context_assembler,
            chat_model=chat_model,
        ),
    )
    graph.add_edge(START, "grocery_builder")
    graph.add_edge("grocery_builder", "price_optimizer")
    graph.add_edge("price_optimizer", END)
    return graph.compile()
