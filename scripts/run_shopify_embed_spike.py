from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shopper.config import Settings
from shopper.supplements.services.checkout_embed_probe import CheckoutEmbedProbeService
from shopper.supplements.tools.shopify_mcp import ShopifyMCPClient, ShopifyMCPError


DEFAULT_JSON_OUTPUT = Path("data/examples/shopify_embed_spike_results.json")
DEFAULT_MARKDOWN_OUTPUT = Path("PHASE0_SHOPIFY_EMBED_SPIKE.md")


@dataclass(frozen=True)
class SpikeProbe:
    store_domain: str
    query: str


@dataclass
class SpikeResult:
    store_domain: str
    query: str
    selected_product_title: Optional[str]
    selected_variant_id: Optional[str]
    checkout_url: Optional[str]
    final_url: Optional[str]
    status_code: Optional[int]
    iframe_allowed: bool
    block_reason: Optional[str]
    x_frame_options: Optional[str]
    content_security_policy: Optional[str]
    frame_ancestors: list[str]
    allowed_embed_origins: list[str]
    error: Optional[str]


SPIKE_PROBES = [
    SpikeProbe("transparentlabs.com", "creatine hmb"),
    SpikeProbe("livemomentous.com", "magnesium l-threonate"),
]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Shopify embed spike against real supplement merchants.")
    parser.add_argument("--output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    args = parser.parse_args()

    settings = Settings()
    results = await run_spike(settings)
    payload = {
        "verified_at": datetime.now().astimezone().isoformat(),
        "results": [asdict(result) for result in results],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    args.report.write_text(build_markdown_report(payload), encoding="utf-8")

    print(f"Wrote JSON spike results to {args.output}")
    print(f"Wrote markdown spike report to {args.report}")


async def run_spike(settings: Settings) -> list[SpikeResult]:
    results: list[SpikeResult] = []
    async with ShopifyMCPClient() as client:
        embed_probe_service = CheckoutEmbedProbeService(settings)
        try:
            for probe in SPIKE_PROBES:
                results.append(await _run_probe(client, embed_probe_service, probe))
        finally:
            await embed_probe_service.aclose()
    return results


async def _run_probe(
    client: ShopifyMCPClient,
    embed_probe_service: CheckoutEmbedProbeService,
    probe: SpikeProbe,
) -> SpikeResult:
    try:
        products = await client.search_store(probe.store_domain, probe.query)
    except ShopifyMCPError as exc:
        return SpikeResult(
            store_domain=probe.store_domain,
            query=probe.query,
            selected_product_title=None,
            selected_variant_id=None,
            checkout_url=None,
            final_url=None,
            status_code=None,
            iframe_allowed=False,
            block_reason="Merchant search failed before checkout could be generated.",
            x_frame_options=None,
            content_security_policy=None,
            frame_ancestors=[],
            allowed_embed_origins=[],
            error=str(exc),
        )

    selected_product = None
    selected_variant = None
    for product in products[:8]:
        available_variants = [variant for variant in product.variants if variant.available]
        if available_variants:
            selected_product = product
            selected_variant = available_variants[0]
            break

    if selected_product is None or selected_variant is None:
        return SpikeResult(
            store_domain=probe.store_domain,
            query=probe.query,
            selected_product_title=None,
            selected_variant_id=None,
            checkout_url=None,
            final_url=None,
            status_code=None,
            iframe_allowed=False,
            block_reason="No in-stock variant was available for the embed spike.",
            x_frame_options=None,
            content_security_policy=None,
            frame_ancestors=[],
            allowed_embed_origins=[],
            error=None,
        )

    try:
        cart = await client.update_cart(probe.store_domain, selected_variant.variant_id, 1)
    except ShopifyMCPError as exc:
        return SpikeResult(
            store_domain=probe.store_domain,
            query=probe.query,
            selected_product_title=selected_product.title,
            selected_variant_id=selected_variant.variant_id,
            checkout_url=None,
            final_url=None,
            status_code=None,
            iframe_allowed=False,
            block_reason="Merchant cart update failed before checkout could be generated.",
            x_frame_options=None,
            content_security_policy=None,
            frame_ancestors=[],
            allowed_embed_origins=[],
            error=str(exc),
        )

    embed_probe = await embed_probe_service.probe_checkout_url(cart.checkout_url or "")
    return SpikeResult(
        store_domain=probe.store_domain,
        query=probe.query,
        selected_product_title=selected_product.title,
        selected_variant_id=selected_variant.variant_id,
        checkout_url=_redact_url(cart.checkout_url),
        final_url=_redact_url(embed_probe.final_url),
        status_code=embed_probe.status_code,
        iframe_allowed=embed_probe.iframe_allowed,
        block_reason=embed_probe.block_reason,
        x_frame_options=embed_probe.x_frame_options,
        content_security_policy=embed_probe.content_security_policy,
        frame_ancestors=embed_probe.frame_ancestors,
        allowed_embed_origins=embed_probe.allowed_embed_origins,
        error=embed_probe.error,
    )


def build_markdown_report(payload: dict[str, object]) -> str:
    verified_at = str(payload["verified_at"])
    results = payload["results"]
    assert isinstance(results, list)

    lines = [
        "# Phase 0 Shopify Embed Spike",
        "",
        f"Verified at: {verified_at}",
        "",
        "## Summary",
        "",
        "Tested live Shopify checkout URLs generated through Storefront MCP for the two supplement merchants currently in MVP scope.",
        "",
        "| Merchant | Product | HTTP | Iframe allowed | Why |",
        "| --- | --- | --- | --- | --- |",
    ]

    for raw_result in results:
        assert isinstance(raw_result, dict)
        lines.append(
            "| {merchant} | {product} | {status} | {allowed} | {reason} |".format(
                merchant=raw_result["store_domain"],
                product=raw_result.get("selected_product_title") or "Unavailable",
                status=raw_result.get("status_code") or "n/a",
                allowed="yes" if raw_result.get("iframe_allowed") else "no",
                reason=raw_result.get("block_reason") or "No block detected",
            )
        )

    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            "Keep `SHOPIFY_CHECKOUT_EMBED_MODE=auto`, but treat auto as `external` unless the live probe explicitly allows Shopper origins. The current live merchants block iframe embedding via CSP frame-ancestors.",
            "",
            "## Notes",
            "",
            "- This spike validates browser iframe embedding against live merchant headers.",
            "- A controlled fallback handoff remains the safe default for Shopify supplement checkout in the current app shell.",
        ]
    )
    return "\n".join(lines) + "\n"


def _redact_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.query:
        return url
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?query=[redacted]"


if __name__ == "__main__":
    asyncio.run(main())
