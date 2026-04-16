from __future__ import annotations

import asyncio

import httpx

from shopper.config import Settings
from shopper.supplements.services.checkout_embed_probe import CheckoutEmbedProbeService


def _settings() -> Settings:
    return Settings(
        SHOPPER_APP_ENV="test",
        LANGSMITH_TRACING=False,
    )


def test_checkout_embed_probe_blocks_when_frame_ancestors_omits_shopper_origins():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-security-policy": (
                    "block-all-mixed-content; "
                    "frame-ancestors 'self' transparent-labs.myshopify.com admin.shopify.com; "
                    "upgrade-insecure-requests;"
                ),
            },
            request=request,
        )

    async def run_test() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            service = CheckoutEmbedProbeService(_settings(), http_client=http_client)
            result = await service.probe_checkout_url("https://www.transparentlabs.com/checkouts/example")

        assert result.status_code == 200
        assert result.iframe_allowed is False
        assert result.frame_ancestors == ["'self'", "transparent-labs.myshopify.com", "admin.shopify.com"]
        assert result.block_reason == "Merchant CSP frame-ancestors does not allow Shopper origins."

    asyncio.run(run_test())


def test_checkout_embed_probe_allows_when_localhost_origin_is_explicitly_permitted():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-security-policy": (
                    "default-src 'self'; frame-ancestors 'self' http://localhost:3000 https://shopper.example;"
                ),
            },
            request=request,
        )

    async def run_test() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            service = CheckoutEmbedProbeService(_settings(), http_client=http_client)
            result = await service.probe_checkout_url("https://merchant.example/checkouts/example")

        assert result.iframe_allowed is True
        assert result.block_reason is None

    asyncio.run(run_test())
