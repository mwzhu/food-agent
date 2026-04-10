from __future__ import annotations

from collections import OrderedDict
from typing import Any, Awaitable, Callable

from langchain_core.messages import AIMessage

from shopper.supplements.agents.nodes.common import coerce_store_cart
from shopper.supplements.events import emit_supplement_event
from shopper.supplements.schemas import StoreCart, SupplementStack
from shopper.supplements.tools.shopify_mcp import update_cart as default_update_cart


UpdateCartFn = Callable[..., Awaitable[Any]]


async def mcp_cart_builder(
    state: dict[str, Any],
    *,
    update_cart_fn: UpdateCartFn = default_update_cart,
) -> dict[str, Any]:
    run_id = state["run_id"]
    await emit_supplement_event(
        run_id=run_id,
        event_type="node_entered",
        phase="checkout",
        node_name="mcp_cart_builder",
        message="Creating Shopify carts for the recommended supplement stack.",
    )

    recommended_stack = SupplementStack.model_validate(state.get("recommended_stack") or {})
    carts = await _build_carts(recommended_stack, update_cart_fn=update_cart_fn)

    await emit_supplement_event(
        run_id=run_id,
        event_type="node_completed",
        phase="checkout",
        node_name="mcp_cart_builder",
        message="Built {count} store carts for checkout handoff.".format(count=len(carts)),
        data={
            "store_count": len(carts),
            "checkout_urls": [cart.checkout_url for cart in carts if cart.checkout_url],
        },
    )

    return {
        "store_carts": [cart.model_dump(mode="json") for cart in carts],
        "messages": [
            AIMessage(
                content="Created checkout-ready carts for {count} stores.".format(count=len(carts))
            )
        ],
    }


async def _build_carts(
    recommended_stack: SupplementStack,
    *,
    update_cart_fn: UpdateCartFn,
) -> list[StoreCart]:
    items_by_store: "OrderedDict[str, list[Any]]" = OrderedDict()
    for item in recommended_stack.items:
        items_by_store.setdefault(item.product.store_domain, []).append(item)

    carts: list[StoreCart] = []
    for store_domain, items in items_by_store.items():
        latest_cart: StoreCart | None = None
        cart_id: str | None = None
        accumulated_errors: list[dict[str, Any]] = []

        for item in items:
            variant = item.product.default_variant
            if variant is None or not variant.variant_id:
                accumulated_errors.append(
                    {
                        "product_id": item.product.product_id,
                        "message": "No variant ID was available for cart creation.",
                    }
                )
                continue
            try:
                raw_cart = await update_cart_fn(
                    store_domain,
                    variant.variant_id,
                    item.quantity,
                    cart_id=cart_id,
                )
                latest_cart = coerce_store_cart(raw_cart)
                cart_id = latest_cart.cart_id
            except Exception as exc:  # pragma: no cover - exercised via unit tests
                accumulated_errors.append(
                    {
                        "product_id": item.product.product_id,
                        "variant_id": variant.variant_id,
                        "message": str(exc),
                    }
                )

        if latest_cart is None:
            carts.append(
                StoreCart(
                    store_domain=store_domain,
                    cart_id=cart_id,
                    checkout_url=None,
                    total_quantity=0,
                    subtotal_amount=None,
                    total_amount=None,
                    currency="USD",
                    lines=[],
                    errors=accumulated_errors,
                    instructions="Retry cart creation for this store before checkout.",
                )
            )
            continue

        carts.append(
            latest_cart.model_copy(
                update={
                    "errors": list(latest_cart.errors) + accumulated_errors,
                }
            )
        )

    return carts
