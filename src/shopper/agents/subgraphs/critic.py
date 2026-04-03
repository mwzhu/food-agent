from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from shopper.agents.nodes import PlanningCriticNode, ShoppingCriticNode
from shopper.agents.state import PlannerState
from shopper.memory import ContextAssembler
from shopper.retrieval import QdrantRecipeStore


def build_planning_critic_subgraph(context_assembler: ContextAssembler, recipe_store: QdrantRecipeStore, chat_model=None):
    graph = StateGraph(PlannerState)
    graph.add_node(
        "critic",
        PlanningCriticNode(
            context_assembler=context_assembler,
            recipe_store=recipe_store,
            chat_model=chat_model,
        ),
    )
    graph.add_edge(START, "critic")
    graph.add_edge("critic", END)
    return graph.compile()


def build_shopping_critic_subgraph(context_assembler: ContextAssembler, chat_model=None):
    graph = StateGraph(PlannerState)
    graph.add_node(
        "critic",
        ShoppingCriticNode(
            context_assembler=context_assembler,
            chat_model=chat_model,
        ),
    )
    graph.add_edge(START, "critic")
    graph.add_edge("critic", END)
    return graph.compile()
