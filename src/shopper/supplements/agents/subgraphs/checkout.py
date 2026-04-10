from __future__ import annotations

from typing import Any, Awaitable, Callable

from langgraph.graph import END, START, StateGraph

from shopper.supplements.agents.nodes import mcp_cart_builder
from shopper.supplements.agents.state import CheckoutSubgraphState
from shopper.supplements.events import emit_supplement_event
from shopper.supplements.schemas import StoreCart
from shopper.supplements.tools.shopify_mcp import update_cart as default_update_cart


UpdateCartFn = Callable[..., Awaitable[Any]]


def build_checkout_subgraph(
    *,
    update_cart_fn: UpdateCartFn = default_update_cart,
):
    graph = StateGraph(CheckoutSubgraphState)

    async def cart_builder_node(state: dict[str, Any]) -> dict[str, Any]:
        result = await mcp_cart_builder(state, update_cart_fn=update_cart_fn)
        carts = [StoreCart.model_validate(item) for item in result.get("store_carts", [])]
        ready_carts = [cart for cart in carts if cart.checkout_url]
        if ready_carts:
            await emit_supplement_event(
                run_id=state["run_id"],
                event_type="approval_requested",
                phase="checkout",
                node_name="mcp_cart_builder",
                message="Checkout links are ready for store approval.",
                data={
                    "store_count": len(ready_carts),
                    "stores": [cart.store_domain for cart in ready_carts],
                    "checkout_urls": [cart.checkout_url for cart in ready_carts if cart.checkout_url],
                },
            )
        return result

    graph.add_node("mcp_cart_builder", cart_builder_node)
    graph.add_edge(START, "mcp_cart_builder")
    graph.add_edge("mcp_cart_builder", END)
    return graph.compile()
