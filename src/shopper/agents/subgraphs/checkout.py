from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from shopper.agents.nodes import BrowserCartBuilderNode, CheckoutExecutorNode, PostCheckoutVerifierNode
from shopper.agents.state import CheckoutSubgraphState


def _route_checkout_stage(state: dict) -> str:
    stage = state.get("checkout_stage")
    if stage == "complete_checkout" and state.get("human_approved"):
        return "checkout_executor"
    if stage == "manual_review":
        return "end"
    if stage == "completed":
        return "post_checkout_verifier"
    return "browser_cart_builder"


def _route_after_checkout_executor(state: dict) -> str:
    if state.get("status") == "failed" or state.get("checkout_stage") == "manual_review":
        return "end"
    return "post_checkout_verifier"


async def _checkout_router(state: dict) -> dict:
    return state


def build_checkout_subgraph(checkout_agent, settings):
    graph = StateGraph(CheckoutSubgraphState)
    graph.add_node("checkout_router", _checkout_router)
    graph.add_node(
        "browser_cart_builder",
        BrowserCartBuilderNode(checkout_agent=checkout_agent, settings=settings),
    )
    graph.add_node(
        "checkout_executor",
        CheckoutExecutorNode(checkout_agent=checkout_agent, settings=settings),
    )
    graph.add_node("post_checkout_verifier", PostCheckoutVerifierNode())
    graph.add_edge(START, "checkout_router")
    graph.add_conditional_edges(
        "checkout_router",
        _route_checkout_stage,
        {
            "browser_cart_builder": "browser_cart_builder",
            "checkout_executor": "checkout_executor",
            "post_checkout_verifier": "post_checkout_verifier",
            "end": END,
        },
    )
    graph.add_edge("browser_cart_builder", END)
    graph.add_conditional_edges(
        "checkout_executor",
        _route_after_checkout_executor,
        {
            "post_checkout_verifier": "post_checkout_verifier",
            "end": END,
        },
    )
    graph.add_edge("post_checkout_verifier", END)
    return graph.compile()
