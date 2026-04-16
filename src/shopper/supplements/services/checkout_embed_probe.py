from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx

from shopper.config import Settings


EMBED_PROBE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class CheckoutEmbedProbeResult:
    checkout_url: str
    final_url: Optional[str]
    status_code: Optional[int]
    iframe_allowed: bool
    block_reason: Optional[str]
    x_frame_options: Optional[str]
    content_security_policy: Optional[str]
    frame_ancestors: list[str]
    allowed_embed_origins: list[str]
    error: Optional[str] = None


class CheckoutEmbedProbeService:
    def __init__(
        self,
        settings: Settings,
        *,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.settings = settings
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            follow_redirects=True,
            timeout=20.0,
            headers={"User-Agent": EMBED_PROBE_USER_AGENT},
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def probe_checkout_url(self, checkout_url: str) -> CheckoutEmbedProbeResult:
        allowed_embed_origins = _resolve_allowed_embed_origins(self.settings)
        try:
            response = await self._client.get(checkout_url)
        except Exception as exc:  # pragma: no cover - network failures are environment-specific
            return CheckoutEmbedProbeResult(
                checkout_url=checkout_url,
                final_url=None,
                status_code=None,
                iframe_allowed=False,
                block_reason="Checkout probe failed before the merchant page loaded.",
                x_frame_options=None,
                content_security_policy=None,
                frame_ancestors=[],
                allowed_embed_origins=allowed_embed_origins,
                error=str(exc),
            )

        final_url = str(response.url)
        x_frame_options = response.headers.get("x-frame-options")
        content_security_policy = response.headers.get("content-security-policy")
        frame_ancestors = _parse_frame_ancestors(content_security_policy)
        iframe_allowed, block_reason = _evaluate_embed_policy(
            final_url=final_url,
            status_code=response.status_code,
            x_frame_options=x_frame_options,
            frame_ancestors=frame_ancestors,
            allowed_embed_origins=allowed_embed_origins,
        )
        return CheckoutEmbedProbeResult(
            checkout_url=checkout_url,
            final_url=final_url,
            status_code=response.status_code,
            iframe_allowed=iframe_allowed,
            block_reason=block_reason,
            x_frame_options=x_frame_options,
            content_security_policy=content_security_policy,
            frame_ancestors=frame_ancestors,
            allowed_embed_origins=allowed_embed_origins,
        )


def _resolve_allowed_embed_origins(settings: Settings) -> list[str]:
    origins = {origin.strip().rstrip("/") for origin in settings.cors_origins.split(",") if origin.strip()}
    if settings.shopify_ucp_profile_url:
        parsed = urlparse(settings.shopify_ucp_profile_url)
        if parsed.scheme and parsed.netloc:
            origins.add(f"{parsed.scheme}://{parsed.netloc}")
    return sorted(origins)


def _parse_frame_ancestors(content_security_policy: Optional[str]) -> list[str]:
    if not content_security_policy:
        return []

    for directive in content_security_policy.split(";"):
        normalized = directive.strip()
        if not normalized:
            continue
        if normalized.lower().startswith("frame-ancestors"):
            _name, _separator, remainder = normalized.partition(" ")
            return [token.strip() for token in remainder.split(" ") if token.strip()]
    return []


def _evaluate_embed_policy(
    *,
    final_url: str,
    status_code: int,
    x_frame_options: Optional[str],
    frame_ancestors: list[str],
    allowed_embed_origins: list[str],
) -> tuple[bool, Optional[str]]:
    if status_code >= 400:
        return False, f"Merchant checkout returned HTTP {status_code}."

    normalized_xfo = (x_frame_options or "").strip().upper()
    if normalized_xfo == "DENY":
        return False, "Merchant returned X-Frame-Options: DENY."
    if normalized_xfo == "SAMEORIGIN":
        return False, "Merchant returned X-Frame-Options: SAMEORIGIN."
    if normalized_xfo.startswith("ALLOW-FROM"):
        allowed_origin = normalized_xfo.partition("ALLOW-FROM")[2].strip()
        if allowed_origin and _matches_allowed_origin(allowed_origin, allowed_embed_origins):
            return True, None
        return False, f"Merchant only allows iframe embedding from {allowed_origin or 'a different origin'}."

    if not frame_ancestors:
        return True, None
    if any(token == "'none'" for token in frame_ancestors):
        return False, "Merchant CSP frame-ancestors is 'none'."
    if any(token == "*" for token in frame_ancestors):
        return True, None
    if any(_frame_ancestor_allows_origin(token, final_url, allowed_embed_origins) for token in frame_ancestors):
        return True, None
    return False, "Merchant CSP frame-ancestors does not allow Shopper origins."


def _frame_ancestor_allows_origin(token: str, final_url: str, allowed_embed_origins: list[str]) -> bool:
    normalized = token.strip().strip('"').strip("'")
    if not normalized:
        return False
    if normalized == "self":
        final_origin = _origin_from_url(final_url)
        return final_origin in allowed_embed_origins
    return _matches_allowed_origin(normalized, allowed_embed_origins)


def _matches_allowed_origin(candidate: str, allowed_embed_origins: list[str]) -> bool:
    normalized_candidate = candidate.rstrip("/")
    if normalized_candidate in allowed_embed_origins:
        return True

    candidate_host = _host_from_origin(normalized_candidate)
    if not candidate_host:
        return False
    return any(_host_from_origin(origin) == candidate_host for origin in allowed_embed_origins)


def _origin_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}"


def _host_from_origin(value: str) -> Optional[str]:
    parsed = urlparse(value)
    if parsed.netloc:
        return parsed.netloc
    if "://" not in value and value:
        return value
    return None
