from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from shopper.supplements.agents.nodes import supplement_critic
from shopper.supplements.agents.state import CriticSubgraphState


def build_critic_subgraph():
    graph = StateGraph(CriticSubgraphState)
    graph.add_node("critic", supplement_critic)
    graph.add_edge(START, "critic")
    graph.add_edge("critic", END)
    return graph.compile()
