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

from shopper.agents.tools.browser_tools import BrowserCheckoutAgent, standalone_result_json
from shopper.config import Settings
from shopper.schemas import GroceryItem, StandaloneCheckoutRequest


def _load_items(path: Path) -> list[GroceryItem]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("items", [])
    return [GroceryItem.model_validate(item) for item in payload]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the standalone browser checkout agent.")
    parser.add_argument("--items", required=True, help="Path to a JSON file containing grocery items.")
    parser.add_argument("--store", required=True, help="Human-readable store name.")
    parser.add_argument("--start-url", required=True, help="Store landing page URL.")
    parser.add_argument("--cart-url", help="Optional cart URL for the store.")
    parser.add_argument("--checkout-url", help="Optional checkout URL for the store.")
    parser.add_argument("--user-id", default="standalone", help="User identifier for artifacts and output.")
    parser.add_argument("--approve", action="store_true", help="Explicitly approve completing checkout.")
    parser.add_argument("--headless", action="store_true", help="Run the browser headlessly.")
    return parser


async def _main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    items = _load_items(Path(args.items))
    settings = Settings()
    agent = BrowserCheckoutAgent(settings)
    request = StandaloneCheckoutRequest(
        user_id=args.user_id,
        store={
            "store": args.store,
            "start_url": args.start_url,
            "cart_url": args.cart_url,
            "checkout_url": args.checkout_url,
            "allowed_domains": [],
        },
        items=items,
        approve=args.approve,
        headless=args.headless or settings.browser_checkout_headless,
        max_steps=settings.browser_checkout_max_steps,
    )
    result = await agent.run(
        request,
        weekly_budget=settings.checkout_max_weekly_total_usd,
        max_order_total=settings.checkout_max_order_total_usd,
        artifact_label=f"standalone-{args.user_id}",
    )
    print(standalone_result_json(result))
    return 0 if result.status != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
