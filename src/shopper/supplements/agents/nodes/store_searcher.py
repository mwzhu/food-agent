from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional, Sequence

from langchain_core.messages import AIMessage

from shopper.supplements.agents.nodes.common import DEFAULT_VERIFIED_STORE_DOMAINS, coerce_shopify_product
from shopper.supplements.events import emit_supplement_event
from shopper.supplements.schemas import CategoryDiscoveryResult, ShopifyProduct, StoreSearchResult, SupplementNeed
from shopper.supplements.tools.shopify_mcp import search_store as default_search_store


SearchStoreFn = Callable[[str, str], Awaitable[list[Any]]]


async def store_searcher(
    state: dict[str, Any],
    *,
    search_store_fn: SearchStoreFn = default_search_store,
    store_domains: Sequence[str] = DEFAULT_VERIFIED_STORE_DOMAINS,
    max_products_per_result: int = 4,
) -> dict[str, Any]:
    run_id = state["run_id"]
    await emit_supplement_event(
        run_id=run_id,
        event_type="node_entered",
        phase="discovery",
        node_name="store_searcher",
        message="Searching verified Shopify stores for supplement matches.",
    )

    needs = [SupplementNeed.model_validate(item) for item in state.get("identified_needs", [])]
    if not needs:
        return {
            "discovery_results": [],
            "messages": [AIMessage(content="No supplement needs were available for store search.")],
        }

    tasks = [
        _search_one(
            need=need,
            store_domain=store_domain,
            query=query,
            search_store_fn=search_store_fn,
            max_products_per_result=max_products_per_result,
        )
        for need in needs
        for query in need.search_queries
        for store_domain in store_domains
    ]
    results = await asyncio.gather(*tasks)

    discovery_results: list[CategoryDiscoveryResult] = []
    for need in needs:
        store_results = [
            result["store_result"]
            for result in results
            if result["category"] == need.category
        ]
        discovery_results.append(
            CategoryDiscoveryResult(
                category=need.category,
                goal=need.goal,
                search_queries=list(need.search_queries),
                store_results=store_results,
            )
        )

    non_empty_results = sum(1 for result in results if result["store_result"].products)
    error_count = sum(1 for result in results if result["error"])
    product_count = sum(len(result["store_result"].products) for result in results)

    await emit_supplement_event(
        run_id=run_id,
        event_type="node_completed",
        phase="discovery",
        node_name="store_searcher",
        message="Searched {store_count} stores across {query_count} queries.".format(
            store_count=len(store_domains),
            query_count=len(tasks),
        ),
        data={
            "result_count": len(results),
            "non_empty_result_count": non_empty_results,
            "error_count": error_count,
            "product_count": product_count,
        },
    )

    return {
        "discovery_results": [result.model_dump(mode="json") for result in discovery_results],
        "messages": [
            AIMessage(
                content="Discovery search found {count} products across {stores} stores.".format(
                    count=product_count,
                    stores=len(store_domains),
                )
            )
        ],
    }


async def _search_one(
    *,
    need: SupplementNeed,
    store_domain: str,
    query: str,
    search_store_fn: SearchStoreFn,
    max_products_per_result: int,
) -> dict[str, Any]:
    products: list[ShopifyProduct] = []
    error: Optional[str] = None
    try:
        raw_products = await search_store_fn(store_domain, query)
        products = [
            coerce_shopify_product(product, store_domain=store_domain)
            for product in raw_products[:max_products_per_result]
        ]
    except Exception as exc:  # pragma: no cover - exercised indirectly in the node tests
        error = str(exc)

    return {
        "category": need.category,
        "store_result": StoreSearchResult(
            store_domain=store_domain,
            query=query,
            products=products,
        ),
        "error": error,
    }
