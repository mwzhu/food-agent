from __future__ import annotations

import asyncio
import json

import httpx

from shopper.supplements.tools.shopify_mcp import ShopifyMCPClient, ShopifyMCPToolError


def test_search_store_parses_products_from_mcp_payload():
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        body = json.loads(request.content.decode())
        assert request.url == httpx.URL("https://ritual.com/api/mcp")
        if body["method"] == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "tools": [
                            {
                                "name": "search_catalog",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "catalog": {
                                            "type": "object",
                                        }
                                    },
                                },
                            }
                        ]
                    },
                },
            )

        assert body["params"]["name"] == "search_catalog"
        assert body["params"]["arguments"]["catalog"]["query"] == "magnesium"
        assert body["params"]["arguments"]["catalog"]["context"]["address_country"] == "US"
        assert body["params"]["arguments"]["catalog"]["signals"]["dev.ucp.user_agent"] == "shopper-supplements-mcp/0.1"
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "products": [
                                        {
                                            "id": "gid://shopify/Product/1",
                                            "title": "Magnesium Glycinate",
                                            "description": {"html": "<p>Gentle <strong>sleep</strong> support.</p>"},
                                            "url": "https://ritual.com/products/magnesium",
                                            "media": [
                                                {
                                                    "type": "image",
                                                    "url": "https://cdn.example.com/magnesium.png",
                                                    "alt_text": "Magnesium bottle",
                                                }
                                            ],
                                            "price_range": {
                                                "min": {"amount": 2400, "currency": "USD"},
                                                "max": {"amount": 2400, "currency": "USD"},
                                            },
                                            "tags": ["sleep"],
                                            "variants": [
                                                {
                                                    "id": "gid://shopify/ProductVariant/10",
                                                    "title": "Default Title",
                                                    "price": {"amount": 2400, "currency": "USD"},
                                                    "availability": {"available": True},
                                                    "media": [
                                                        {
                                                            "type": "image",
                                                            "url": "https://cdn.example.com/magnesium-variant.png",
                                                        }
                                                    ],
                                                }
                                            ],
                                        }
                                    ]
                                }
                            ),
                        }
                    ]
                },
            },
        )

    async def run_test() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = ShopifyMCPClient(http_client=http_client)
            products = await client.search_store("https://ritual.com", "magnesium")

        assert len(products) == 1
        assert products[0].title == "Magnesium Glycinate"
        assert products[0].description == "Gentle sleep support."
        assert products[0].image_url == "https://cdn.example.com/magnesium.png"
        assert products[0].price_range.min_price == "24.00"
        assert products[0].price_range.currency == "USD"
        assert products[0].variants[0].variant_id == "gid://shopify/ProductVariant/10"
        assert products[0].variants[0].price == "24.00"
        assert request_count == 2

    asyncio.run(run_test())


def test_search_store_falls_back_to_legacy_search_tool():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        if body["method"] == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "tools": [
                            {
                                "name": "search_shop_catalog",
                                "inputSchema": {
                                    "type": "object",
                                },
                            }
                        ]
                    },
                },
            )

        assert body["params"]["name"] == "search_shop_catalog"
        assert body["params"]["arguments"]["query"] == "magnesium"
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "products": [
                                        {
                                            "product_id": "gid://shopify/Product/1",
                                            "title": "Magnesium Glycinate",
                                            "description": "Gentle sleep support.",
                                            "url": "https://ritual.com/products/magnesium",
                                            "image_url": "https://cdn.example.com/magnesium.png",
                                            "image_alt_text": "Magnesium bottle",
                                            "price_range": {
                                                "min": "24.00",
                                                "max": "24.00",
                                                "currency": "USD",
                                            },
                                            "product_type": "Supplement",
                                            "tags": ["sleep"],
                                            "variants": [
                                                {
                                                    "variant_id": "gid://shopify/ProductVariant/10",
                                                    "title": "Default Title",
                                                    "price": "24.00",
                                                    "currency": "USD",
                                                    "available": True,
                                                }
                                            ],
                                        }
                                    ]
                                }
                            ),
                        }
                    ]
                },
            },
        )

    async def run_test() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = ShopifyMCPClient(http_client=http_client)
            products = await client.search_store("ritual.com", "magnesium")

        assert len(products) == 1
        assert products[0].title == "Magnesium Glycinate"
        assert products[0].price_range.min_price == "24.00"

    asyncio.run(run_test())


def test_update_cart_uses_product_variant_id_and_parses_cart_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["params"]["name"] == "update_cart"
        assert body["params"]["arguments"] == {
            "add_items": [
                {
                    "product_variant_id": "gid://shopify/ProductVariant/11",
                    "quantity": 2,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "instructions": "Use the checkout URL when ready.",
                                    "cart": {
                                        "id": "gid://shopify/Cart/cart-1?key=abc",
                                        "checkout_url": "https://example.com/cart/c/cart-1?key=abc",
                                        "created_at": "2026-04-09T00:00:00Z",
                                        "updated_at": "2026-04-09T00:00:00Z",
                                        "total_quantity": 2,
                                        "cost": {
                                            "subtotal_amount": {"amount": "58.00", "currency": "USD"},
                                            "total_amount": {"amount": "58.00", "currency": "USD"},
                                        },
                                        "lines": [
                                            {
                                                "id": "gid://shopify/CartLine/line-1",
                                                "quantity": 2,
                                                "cost": {
                                                    "subtotal_amount": {"amount": "58.00", "currency": "USD"},
                                                    "total_amount": {"amount": "58.00", "currency": "USD"},
                                                },
                                                "merchandise": {
                                                    "id": "gid://shopify/ProductVariant/11",
                                                    "title": "Default Title",
                                                    "product": {
                                                        "id": "gid://shopify/Product/22",
                                                        "title": "Creatine",
                                                    },
                                                },
                                            }
                                        ],
                                    },
                                    "errors": [],
                                }
                            ),
                        }
                    ]
                },
            },
        )

    async def run_test() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = ShopifyMCPClient(http_client=http_client)
            cart = await client.update_cart("transparentlabs.com", "gid://shopify/ProductVariant/11", 2)

        assert cart.cart_id == "gid://shopify/Cart/cart-1?key=abc"
        assert cart.checkout_url == "https://example.com/cart/c/cart-1?key=abc"
        assert cart.total_quantity == 2
        assert cart.lines[0].product_title == "Creatine"

    asyncio.run(run_test())


def test_get_cart_raises_structured_tool_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "cart": {},
                                    "errors": [
                                        {
                                            "field": ["cart_id"],
                                            "message": "Cart not found.",
                                        }
                                    ],
                                }
                            ),
                        }
                    ],
                },
            },
        )

    async def run_test() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = ShopifyMCPClient(http_client=http_client)
            try:
                await client.get_cart("goli.com", "missing-cart")
            except ShopifyMCPToolError as exc:
                assert exc.store_domain == "goli.com"
                assert exc.tool_name == "get_cart"
                assert exc.details["errors"][0]["message"] == "Cart not found."
            else:  # pragma: no cover - defensive
                raise AssertionError("Expected ShopifyMCPToolError to be raised.")

    asyncio.run(run_test())
