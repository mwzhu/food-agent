from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from itertools import count
from typing import Any, Optional
from urllib.parse import urlparse

import httpx


DEFAULT_SEARCH_CONTEXT = (
    "Supplement shopping assistant. Return accurate product names, prices, "
    "variant IDs, descriptions, and availability."
)
DEFAULT_SEARCH_LIMIT = 10
DEFAULT_ADDRESS_COUNTRY = "US"
DEFAULT_LANGUAGE = "en"
DEFAULT_CURRENCY = "USD"
HTML_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class ShopifyPriceRange:
    min_price: str
    max_price: str
    currency: str


@dataclass(frozen=True)
class ShopifyProductVariant:
    variant_id: str
    title: str
    price: str
    currency: str
    available: bool
    image_url: Optional[str] = None


@dataclass(frozen=True)
class ShopifyProduct:
    product_id: str
    title: str
    description: str
    url: str
    image_url: Optional[str]
    image_alt_text: Optional[str]
    product_type: str
    tags: list[str]
    price_range: ShopifyPriceRange
    variants: list[ShopifyProductVariant]


@dataclass(frozen=True)
class ShopifyCartLine:
    line_id: str
    quantity: int
    product_title: str
    product_id: str
    variant_id: str
    variant_title: str
    subtotal_amount: Optional[str]
    total_amount: Optional[str]
    currency: Optional[str]


@dataclass(frozen=True)
class ShopifyCartResult:
    store_domain: str
    cart_id: Optional[str]
    checkout_url: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    total_quantity: int
    subtotal_amount: Optional[str]
    total_amount: Optional[str]
    currency: Optional[str]
    lines: list[ShopifyCartLine]
    errors: list[dict[str, Any]]
    instructions: Optional[str]


class ShopifyMCPError(RuntimeError):
    """Raised when a Shopify Storefront MCP request cannot be completed."""


class ShopifyMCPToolError(ShopifyMCPError):
    """Raised when a Storefront MCP tool returns a structured error."""

    def __init__(
        self,
        store_domain: str,
        tool_name: str,
        message: str,
        *,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(f"{store_domain} {tool_name} failed: {message}")
        self.store_domain = store_domain
        self.tool_name = tool_name
        self.details = details or {}


@dataclass(frozen=True)
class ShopifyMCPToolInfo:
    name: str
    input_schema: dict[str, Any]


class ShopifyMCPClient:
    def __init__(
        self,
        *,
        timeout: float = 20.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "shopper-supplements-mcp/0.1",
            },
        )
        self._request_ids = count(1)
        self._search_tool_cache: dict[str, ShopifyMCPToolInfo] = {}

    async def __aenter__(self) -> "ShopifyMCPClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search_store(
        self,
        store_domain: str,
        query: str,
        *,
        context: str = DEFAULT_SEARCH_CONTEXT,
    ) -> list[ShopifyProduct]:
        query = query.strip()
        if not query:
            raise ValueError("query must not be blank")

        search_tool = await self._resolve_search_tool(store_domain)
        payload = await self._call_tool(
            store_domain,
            search_tool.name,
            _build_search_arguments(
                tool_name=search_tool.name,
                query=query,
                context=context,
            ),
        )
        return [_parse_product(product) for product in payload.get("products", [])]

    async def update_cart(
        self,
        store_domain: str,
        variant_id: str,
        quantity: int,
        *,
        cart_id: Optional[str] = None,
    ) -> ShopifyCartResult:
        if quantity < 1:
            raise ValueError("quantity must be at least 1")
        if not variant_id.strip():
            raise ValueError("variant_id must not be blank")

        arguments: dict[str, Any] = {
            "add_items": [
                {
                    "product_variant_id": variant_id,
                    "quantity": quantity,
                }
            ]
        }
        if cart_id:
            arguments["cart_id"] = cart_id

        payload = await self._call_tool(store_domain, "update_cart", arguments)
        return _parse_cart_result(store_domain, payload)

    async def get_cart(self, store_domain: str, cart_id: str) -> ShopifyCartResult:
        if not cart_id.strip():
            raise ValueError("cart_id must not be blank")

        payload = await self._call_tool(
            store_domain,
            "get_cart",
            {"cart_id": cart_id},
        )
        return _parse_cart_result(store_domain, payload)

    async def _call_tool(
        self,
        store_domain: str,
        tool_name: str,
        arguments: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        normalized_domain = _normalize_store_domain(store_domain)
        request_payload = {
            "jsonrpc": "2.0",
            "id": next(self._request_ids),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments or {},
            },
        }

        response = await self._client.post(
            f"https://{normalized_domain}/api/mcp",
            json=request_payload,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("error"):
            error_message = payload["error"].get("message", "Unknown JSON-RPC error.")
            raise ShopifyMCPToolError(normalized_domain, tool_name, error_message, details=payload["error"])

        result = payload.get("result")
        if not isinstance(result, dict):
            raise ShopifyMCPError(f"{normalized_domain} {tool_name} returned no result payload.")

        raw_text = _extract_text_content(result.get("content") or [])
        parsed_payload = _parse_text_payload(raw_text)
        if result.get("isError"):
            raise ShopifyMCPToolError(
                normalized_domain,
                tool_name,
                _extract_error_message(parsed_payload, raw_text),
                details=parsed_payload,
            )
        return parsed_payload

    async def _resolve_search_tool(self, store_domain: str) -> ShopifyMCPToolInfo:
        normalized_domain = _normalize_store_domain(store_domain)
        cached = self._search_tool_cache.get(normalized_domain)
        if cached is not None:
            return cached

        tools = await self._list_tools(normalized_domain)
        search_tool = _select_search_tool(tools)
        self._search_tool_cache[normalized_domain] = search_tool
        return search_tool

    async def _list_tools(self, normalized_domain: str) -> list[ShopifyMCPToolInfo]:
        response = await self._client.post(
            f"https://{normalized_domain}/api/mcp",
            json={
                "jsonrpc": "2.0",
                "id": next(self._request_ids),
                "method": "tools/list",
                "params": {},
            },
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            error_message = payload["error"].get("message", "Unknown JSON-RPC error.")
            raise ShopifyMCPError(f"{normalized_domain} tools/list failed: {error_message}")

        result = payload.get("result")
        if not isinstance(result, dict):
            raise ShopifyMCPError(f"{normalized_domain} tools/list returned no result payload.")

        tools: list[ShopifyMCPToolInfo] = []
        for raw_tool in result.get("tools") or []:
            if not isinstance(raw_tool, dict):
                continue
            name = str(raw_tool.get("name") or "").strip()
            if not name:
                continue
            input_schema = raw_tool.get("inputSchema")
            tools.append(
                ShopifyMCPToolInfo(
                    name=name,
                    input_schema=input_schema if isinstance(input_schema, dict) else {},
                )
            )

        if not tools:
            raise ShopifyMCPError(f"{normalized_domain} tools/list returned no tools.")
        return tools


async def search_store(
    store_domain: str,
    query: str,
    *,
    context: str = DEFAULT_SEARCH_CONTEXT,
) -> list[ShopifyProduct]:
    async with ShopifyMCPClient() as client:
        return await client.search_store(store_domain, query, context=context)


async def update_cart(
    store_domain: str,
    variant_id: str,
    quantity: int,
    *,
    cart_id: Optional[str] = None,
) -> ShopifyCartResult:
    async with ShopifyMCPClient() as client:
        return await client.update_cart(store_domain, variant_id, quantity, cart_id=cart_id)


async def get_cart(store_domain: str, cart_id: str) -> ShopifyCartResult:
    async with ShopifyMCPClient() as client:
        return await client.get_cart(store_domain, cart_id)


def _normalize_store_domain(store_domain: str) -> str:
    candidate = store_domain.strip()
    if not candidate:
        raise ValueError("store_domain must not be blank")
    if "://" in candidate:
        parsed = urlparse(candidate)
        candidate = parsed.netloc or parsed.path
    return candidate.rstrip("/")


def _select_search_tool(tools: list[ShopifyMCPToolInfo]) -> ShopifyMCPToolInfo:
    preferred_tool_names = ("search_catalog", "search_shop_catalog")
    for tool_name in preferred_tool_names:
        for tool in tools:
            if tool.name == tool_name:
                return tool
    available = ", ".join(sorted(tool.name for tool in tools))
    raise ShopifyMCPError(
        "Storefront MCP search tool not found. Available tools: {tools}".format(tools=available or "none")
    )


def _build_search_arguments(*, tool_name: str, query: str, context: str) -> dict[str, Any]:
    if tool_name == "search_catalog":
        return {
            "catalog": {
                "query": query,
                "context": {
                    "address_country": DEFAULT_ADDRESS_COUNTRY,
                    "language": DEFAULT_LANGUAGE,
                    "currency": DEFAULT_CURRENCY,
                    "intent": context,
                },
                "signals": {
                    "dev.ucp.user_agent": "shopper-supplements-mcp/0.1",
                },
                "pagination": {
                    "limit": DEFAULT_SEARCH_LIMIT,
                },
            }
        }
    return {"query": query, "context": context}


def _extract_text_content(content: list[dict[str, Any]]) -> str:
    text_parts = [
        item.get("text", "")
        for item in content
        if isinstance(item, dict) and item.get("type") == "text" and item.get("text")
    ]
    if not text_parts:
        raise ShopifyMCPError("Storefront MCP returned no text content.")
    return "\n".join(text_parts)


def _parse_text_payload(raw_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return {"message": raw_text}
    return parsed if isinstance(parsed, dict) else {"data": parsed}


def _extract_error_message(parsed_payload: dict[str, Any], raw_text: str) -> str:
    errors = parsed_payload.get("errors")
    if isinstance(errors, list):
        messages = [error.get("message") for error in errors if isinstance(error, dict) and error.get("message")]
        if messages:
            return "; ".join(messages)
    message = parsed_payload.get("message")
    if isinstance(message, str) and message.strip():
        return message
    return raw_text


def _parse_product(product: dict[str, Any]) -> ShopifyProduct:
    price_range = product.get("price_range") or {}
    image_url, image_alt_text = _parse_media(product.get("media") or [])
    return ShopifyProduct(
        product_id=product.get("product_id") or product.get("id", ""),
        title=product.get("title", ""),
        description=_normalize_description(product.get("description", "")),
        url=product.get("url", ""),
        image_url=product.get("image_url") or image_url,
        image_alt_text=product.get("image_alt_text") or image_alt_text,
        product_type=product.get("product_type", ""),
        tags=list(product.get("tags") or []),
        price_range=ShopifyPriceRange(
            min_price=_normalize_price_amount(price_range.get("min")),
            max_price=_normalize_price_amount(price_range.get("max")),
            currency=_extract_currency(price_range),
        ),
        variants=[
            ShopifyProductVariant(
                variant_id=variant.get("variant_id") or variant.get("id", ""),
                title=variant.get("title", ""),
                price=_normalize_price_amount(variant.get("price")),
                currency=_extract_currency(variant.get("price") or variant),
                available=_extract_availability(variant),
                image_url=variant.get("image_url") or _parse_media(variant.get("media") or [])[0],
            )
            for variant in (product.get("variants") or [])
        ],
    )


def _parse_cart_result(store_domain: str, payload: dict[str, Any]) -> ShopifyCartResult:
    cart = payload.get("cart") or {}
    cost = cart.get("cost") or {}
    subtotal_amount = cost.get("subtotal_amount") or {}
    total_amount = cost.get("total_amount") or {}
    currency = total_amount.get("currency") or subtotal_amount.get("currency")

    return ShopifyCartResult(
        store_domain=store_domain,
        cart_id=cart.get("id"),
        checkout_url=cart.get("checkout_url"),
        created_at=cart.get("created_at"),
        updated_at=cart.get("updated_at"),
        total_quantity=int(cart.get("total_quantity") or 0),
        subtotal_amount=_normalize_price_amount(subtotal_amount.get("amount")),
        total_amount=_normalize_price_amount(total_amount.get("amount")),
        currency=currency,
        lines=[_parse_cart_line(line) for line in (cart.get("lines") or [])],
        errors=list(payload.get("errors") or []),
        instructions=payload.get("instructions"),
    )


def _parse_cart_line(line: dict[str, Any]) -> ShopifyCartLine:
    cost = line.get("cost") or {}
    subtotal_amount = cost.get("subtotal_amount") or {}
    total_amount = cost.get("total_amount") or {}
    merchandise = line.get("merchandise") or {}
    product = merchandise.get("product") or {}
    currency = total_amount.get("currency") or subtotal_amount.get("currency")

    return ShopifyCartLine(
        line_id=line.get("id", ""),
        quantity=int(line.get("quantity") or 0),
        product_title=product.get("title", ""),
        product_id=product.get("id", ""),
        variant_id=merchandise.get("id", ""),
        variant_title=merchandise.get("title", ""),
        subtotal_amount=_normalize_price_amount(subtotal_amount.get("amount")),
        total_amount=_normalize_price_amount(total_amount.get("amount")),
        currency=currency,
    )


def _normalize_description(value: Any) -> str:
    if isinstance(value, str):
        text = value
    elif isinstance(value, dict):
        text = str(value.get("html") or value.get("text") or value.get("plain_text") or "")
    else:
        text = str(value or "")
    if not text:
        return ""
    normalized = html.unescape(HTML_TAG_RE.sub(" ", text))
    return " ".join(normalized.split())


def _normalize_price_amount(value: Any) -> str:
    if isinstance(value, dict):
        return _normalize_price_amount(value.get("amount"))
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return f"{value / 100:.2f}"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".") if not value.is_integer() else f"{value:.1f}"
    text = str(value).strip()
    return text


def _extract_currency(value: Any) -> str:
    if isinstance(value, dict):
        currency = value.get("currency")
        if currency:
            return str(currency)
        for key in ("min", "max", "price", "subtotal_amount", "total_amount"):
            nested = value.get(key)
            if isinstance(nested, dict) and nested.get("currency"):
                return str(nested["currency"])
    return ""


def _extract_availability(variant: dict[str, Any]) -> bool:
    if "available" in variant:
        return bool(variant.get("available"))
    availability = variant.get("availability")
    if isinstance(availability, dict):
        return bool(availability.get("available"))
    return False


def _parse_media(media_items: list[dict[str, Any]]) -> tuple[Optional[str], Optional[str]]:
    for media_item in media_items:
        if not isinstance(media_item, dict):
            continue
        if media_item.get("type") != "image":
            continue
        return media_item.get("url"), media_item.get("alt_text")
    return None, None
