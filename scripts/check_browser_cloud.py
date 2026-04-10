from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shopper.agents.tools.browser_tools import BrowserUseUnavailableError, browser_use_runtime_status
from shopper.config import Settings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke-test the Browser Use cloud browser configuration.")
    parser.add_argument("--url", default="https://example.com", help="URL to open in the cloud browser.")
    return parser


async def _main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    settings = Settings()

    available, reason = browser_use_runtime_status()
    if not available:
        raise BrowserUseUnavailableError(reason or "browser-use is unavailable.")

    if not settings.browser_checkout_use_cloud:
        raise BrowserUseUnavailableError("SHOPPER_BROWSER_CHECKOUT_USE_CLOUD must be true for this smoke test.")

    if not settings.browser_use_api_key:
        raise BrowserUseUnavailableError("BROWSER_USE_API_KEY must be set for the cloud browser smoke test.")

    from browser_use import Browser

    browser = Browser(
        use_cloud=True,
        headless=settings.browser_checkout_headless,
        cloud_profile_id=settings.browser_checkout_cloud_profile_id or None,
        cloud_proxy_country_code=settings.browser_checkout_cloud_proxy_country_code or None,
        cloud_timeout=settings.browser_checkout_cloud_timeout_minutes,
        captcha_solver=settings.browser_checkout_captcha_solver,
    )

    try:
        await browser.start()
        page = await browser.get_current_page()
        await page.goto(args.url)
        result = {
            "requested_url": args.url,
            "page_title": await page.get_title(),
            "resolved_url": await page.get_url(),
            "cloud_profile_id": settings.browser_checkout_cloud_profile_id or None,
            "proxy_country_code": settings.browser_checkout_cloud_proxy_country_code or None,
            "timeout_minutes": settings.browser_checkout_cloud_timeout_minutes,
        }
        print(json.dumps(result, indent=2))
        return 0
    finally:
        await browser.stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
