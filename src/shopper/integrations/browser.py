from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from shopper.schemas import BasketPlan, CheckoutResult


@dataclass
class BrowserSession:
    profile_id: str
    provider: str = "walmart"


class BrowserExecutor:
    async def restore_session(self, session: BrowserSession) -> dict:
        return {"profile_id": session.profile_id, "provider": session.provider, "restored": True}

    async def build_cart(self, session: BrowserSession, basket_plan: BasketPlan) -> dict:
        return {
            "profile_id": session.profile_id,
            "items": [item.item_name for item in basket_plan.items],
            "estimated_total": basket_plan.estimated_total,
        }

    async def complete_checkout(self, session: BrowserSession, basket_plan: BasketPlan) -> CheckoutResult:
        return CheckoutResult(
            status="completed",
            confirmation_id=f"wm-{uuid4().hex[:10]}",
            message=f"Mock checkout completed for {len(basket_plan.items)} items.",
        )

