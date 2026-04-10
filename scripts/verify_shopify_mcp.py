from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shopper.supplements.tools.shopify_mcp import ShopifyMCPClient, ShopifyMCPError, ShopifyMCPToolError


DEFAULT_OUTPUT_PATH = Path("data/examples/shopify_mcp_spike_results.json")
CHECKOUT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class StoreProbe:
    store_domain: str
    query: str


@dataclass
class StoreVerificationResult:
    store_domain: str
    query: str
    verified: bool
    search_result_count: int
    selected_product_title: Optional[str] = None
    selected_variant_id: Optional[str] = None
    product_price: Optional[str] = None
    currency: Optional[str] = None
    cart_id: Optional[str] = None
    checkout_url_reachable: bool = False
    checkout_http_status: Optional[int] = None
    checkout_final_url: Optional[str] = None
    checkout_page_title: Optional[str] = None
    checkout_contains_product_title: bool = False
    failure_reason: Optional[str] = None
    attempted_products: list[str] | None = None


PRIMARY_PROBES = [
    StoreProbe("ritual.com", "sleep"),
    StoreProbe("transparentlabs.com", "creatine hmb"),
    StoreProbe("livemomentous.com", "magnesium l-threonate"),
]

FALLBACK_PROBES = [
    StoreProbe("goli.com", "ashwagandha"),
    StoreProbe("vitalproteins.com", "collagen peptides"),
    StoreProbe("mudwtr.com", "adaptogens"),
]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Shopify Storefront MCP search and cart flows.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Where to write the spike summary JSON (default: {DEFAULT_OUTPUT_PATH}).",
    )
    parser.add_argument(
        "--verified-store-count",
        type=int,
        default=3,
        help="Stop once this many stores pass search -> cart -> checkout verification.",
    )
    args = parser.parse_args()

    results = await verify_candidate_stores(args.verified_store_count)
    payload = {
        "verified_at": datetime.now().astimezone().isoformat(),
        "verified_store_domains": [result.store_domain for result in results if result.verified],
        "results": [asdict(result) for result in results],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Wrote spike summary to {args.output}")
    print("Verified stores:")
    for domain in payload["verified_store_domains"]:
        print(f"- {domain}")

    unverified = [result for result in results if not result.verified]
    if unverified:
        print("Unverified stores:")
        for result in unverified:
            print(f"- {result.store_domain}: {result.failure_reason}")


async def verify_candidate_stores(verified_store_count: int) -> list[StoreVerificationResult]:
    results: list[StoreVerificationResult] = []
    verified = 0

    async with ShopifyMCPClient() as client:
        for probe in [*PRIMARY_PROBES, *FALLBACK_PROBES]:
            result = await verify_store(client, probe)
            results.append(result)
            if result.verified:
                verified += 1
                if verified >= verified_store_count:
                    break

    return results


async def verify_store(client: ShopifyMCPClient, probe: StoreProbe) -> StoreVerificationResult:
    try:
        products = await client.search_store(probe.store_domain, probe.query)
    except ShopifyMCPError as exc:
        return StoreVerificationResult(
            store_domain=probe.store_domain,
            query=probe.query,
            verified=False,
            search_result_count=0,
            failure_reason=str(exc),
            attempted_products=[],
        )

    attempted_products: list[str] = []
    last_failure_reason: Optional[str] = None

    for product in products[:8]:
        attempted_products.append(product.title)
        available_variants = [variant for variant in product.variants if variant.available]
        if not available_variants:
            continue

        selected_variant = available_variants[0]
        try:
            cart = await client.update_cart(probe.store_domain, selected_variant.variant_id, 1)
        except ShopifyMCPToolError as exc:
            last_failure_reason = _tool_error_reason(exc)
            continue

        try:
            fetched_cart = await client.get_cart(probe.store_domain, cart.cart_id or "")
        except ShopifyMCPError as exc:
            last_failure_reason = str(exc)
            continue
        checkout_verification = await verify_checkout_url(cart.checkout_url, product.title)
        verified = (
            fetched_cart.total_quantity >= 1
            and fetched_cart.checkout_url == cart.checkout_url
            and checkout_verification["reachable"]
        )

        return StoreVerificationResult(
            store_domain=probe.store_domain,
            query=probe.query,
            verified=verified,
            search_result_count=len(products),
            selected_product_title=product.title,
            selected_variant_id=selected_variant.variant_id,
            product_price=selected_variant.price,
            currency=selected_variant.currency,
            cart_id=_redact_cart_id(cart.cart_id),
            checkout_url_reachable=bool(checkout_verification["reachable"]),
            checkout_http_status=checkout_verification["status_code"],
            checkout_final_url=_redact_url(checkout_verification["final_url"]),
            checkout_page_title=checkout_verification["page_title"],
            checkout_contains_product_title=bool(checkout_verification["contains_product_title"]),
            failure_reason=None if verified else "Checkout URL was not reachable.",
            attempted_products=attempted_products,
        )

    return StoreVerificationResult(
        store_domain=probe.store_domain,
        query=probe.query,
        verified=False,
        search_result_count=len(products),
        failure_reason=last_failure_reason if products else "Search returned no products.",
        attempted_products=attempted_products,
    )


async def verify_checkout_url(checkout_url: Optional[str], product_title: str) -> dict[str, object]:
    if not checkout_url:
        return {
            "reachable": False,
            "status_code": None,
            "final_url": None,
            "page_title": None,
            "contains_product_title": False,
        }

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=20.0,
            headers={"User-Agent": CHECKOUT_USER_AGENT},
        ) as client:
            async with client.stream("GET", checkout_url) as response:
                status_code = response.status_code
                final_url = str(response.url)
                chunks: list[str] = []
                size = 0
                async for chunk in response.aiter_text():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size >= 65536:
                        break
    except Exception as exc:
        return {
            "reachable": False,
            "status_code": None,
            "final_url": None,
            "page_title": None,
            "contains_product_title": False,
            "error": str(exc),
        }

    html = "".join(chunks)
    page_title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    page_title = None
    if page_title_match:
        page_title = re.sub(r"\s+", " ", page_title_match.group(1)).strip()

    return {
        "reachable": status_code < 400,
        "status_code": status_code,
        "final_url": final_url,
        "page_title": page_title,
        "contains_product_title": product_title.lower() in html.lower(),
    }


def _tool_error_reason(exc: ShopifyMCPToolError) -> str:
    errors = exc.details.get("errors")
    if isinstance(errors, list):
        messages = [error.get("message") for error in errors if isinstance(error, dict) and error.get("message")]
        if messages:
            return "; ".join(messages)
    return str(exc)


def _redact_cart_id(cart_id: Optional[str]) -> Optional[str]:
    if not cart_id:
        return None
    if "?key=" not in cart_id:
        return cart_id
    prefix, _separator, _suffix = cart_id.partition("?key=")
    return f"{prefix}?key=[redacted]"


def _redact_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.query:
        return url
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?query=[redacted]"


if __name__ == "__main__":
    asyncio.run(main())
