from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from shopper.agents.events import emit_run_event
from shopper.agents.tools import BrowserCheckoutAgent
from shopper.agents.tools.browser_tools import CheckoutFlowError
from shopper.config import Settings
from shopper.schemas import ContextMetadata, PurchaseOrder, StandaloneCheckoutRequest


def _phase_statuses(checkout: str) -> dict[str, str]:
    return {
        "memory": "completed",
        "planning": "completed",
        "shopping": "completed",
        "checkout": checkout,
    }


def _build_request(state: Dict[str, Any], settings: Settings) -> StandaloneCheckoutRequest:
    existing_order = PurchaseOrder.model_validate((state.get("purchase_orders") or [])[0])
    return StandaloneCheckoutRequest(
        user_id=state["user_id"],
        store={
            "store": existing_order.store,
            "start_url": existing_order.store_url,
            "cart_url": existing_order.cart_url,
            "checkout_url": existing_order.checkout_url,
            "allowed_domains": existing_order.allowed_domains,
        },
        items=existing_order.requested_items or state.get("grocery_list", []),
        approve=False,
        headless=settings.browser_checkout_headless,
        max_steps=settings.browser_checkout_max_steps,
    )


@dataclass
class BrowserCartBuilderNode:
    checkout_agent: BrowserCheckoutAgent
    settings: Settings

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_entered",
            phase="checkout",
            node_name="browser_cart_builder",
            message="Preparing the browser checkout cart.",
        )

        request = _build_request(state, self.settings)
        weekly_budget = min(
            float(state["user_profile"].get("budget_weekly", self.settings.checkout_max_weekly_total_usd)),
            self.settings.checkout_max_weekly_total_usd,
        )
        order = await self.checkout_agent.prepare_order(
            request,
            weekly_budget=weekly_budget,
            max_order_total=self.settings.checkout_max_order_total_usd,
            artifact_label=state["run_id"],
        )

        existing_order = PurchaseOrder.model_validate((state.get("purchase_orders") or [])[0])
        order = order.model_copy(
            update={
                "order_id": existing_order.order_id,
                "store": existing_order.store,
                "store_url": existing_order.store_url,
                "checkout_url": existing_order.checkout_url,
                "allowed_domains": existing_order.allowed_domains,
            }
        )
        verification = order.verification
        metadata = ContextMetadata(
            node_name="browser_cart_builder",
            tokens_used=0,
            token_budget=0,
            fields_included=["grocery_list", "purchase_orders", "user_profile"],
            fields_dropped=[],
            retrieved_memory_ids=[],
        )

        if order.status in {"failed", "manual_review"}:
            await emit_run_event(
                run_id=state["run_id"],
                event_type="error",
                phase="checkout",
                node_name="browser_cart_builder",
                message=order.failure_reason or "Checkout cart build failed.",
                data={"order_id": order.order_id, "status": order.status},
            )
            await emit_run_event(
                run_id=state["run_id"],
                event_type="run_completed",
                phase="checkout",
                node_name="browser_cart_builder",
                message="Checkout moved to manual review.",
                data={"status": "failed"},
            )
            return {
                "purchase_orders": [order.model_dump(mode="json")],
                "context_metadata": [metadata.model_dump(mode="json")],
                "status": "failed",
                "current_node": "browser_cart_builder",
                "current_phase": "checkout",
                "phase_statuses": _phase_statuses("failed"),
                "checkout_stage": "manual_review",
                "cart_verified": bool(verification and verification.passed),
                "cart_screenshot_path": order.cart_screenshot_path,
                "latest_error": order.failure_reason,
            }

        await emit_run_event(
            run_id=state["run_id"],
            event_type="approval_requested",
            phase="checkout",
            node_name="browser_cart_builder",
            message="Cart is ready for approval before purchase.",
            data={
                "order_id": order.order_id,
                "store": order.store,
                "total_cost": order.total_cost,
                "cart_screenshot_path": order.cart_screenshot_path,
                "cart_verified": bool(verification and verification.passed),
                "discrepancies": verification.model_dump(mode="json") if verification else None,
            },
        )
        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_completed",
            phase="checkout",
            node_name="browser_cart_builder",
            message="Cart prepared and waiting for approval.",
            data={"order_id": order.order_id, "status": "awaiting_approval"},
        )
        return {
            "purchase_orders": [order.model_dump(mode="json")],
            "context_metadata": [metadata.model_dump(mode="json")],
            "status": "awaiting_approval",
            "current_node": "browser_cart_builder",
            "current_phase": "checkout",
            "phase_statuses": _phase_statuses("running"),
            "human_approved": None,
            "approval_reason": None,
            "checkout_stage": "awaiting_approval",
            "cart_verified": bool(verification and verification.passed),
            "cart_screenshot_path": order.cart_screenshot_path,
            "latest_error": None,
        }


@dataclass
class CheckoutExecutorNode:
    checkout_agent: BrowserCheckoutAgent
    settings: Settings

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        order = PurchaseOrder.model_validate((state.get("purchase_orders") or [])[0])
        request = _build_request(state, self.settings)
        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_entered",
            phase="checkout",
            node_name="checkout_executor",
            message="Finishing checkout after human approval.",
            data={"order_id": order.order_id},
        )
        try:
            completed_order = await self.checkout_agent.complete_order(
                request,
                order.model_copy(update={"status": "approved"}),
                artifact_label=state["run_id"],
            )
        except CheckoutFlowError as exc:
            failed_order = order.model_copy(
                update={
                    "status": "failed",
                    "failure_code": exc.code,
                    "failure_reason": str(exc),
                }
            )
            await emit_run_event(
                run_id=state["run_id"],
                event_type="error",
                phase="checkout",
                node_name="checkout_executor",
                message=str(exc),
                data={"order_id": failed_order.order_id, "failure_code": exc.code},
            )
            await emit_run_event(
                run_id=state["run_id"],
                event_type="run_completed",
                phase="checkout",
                node_name="checkout_executor",
                message="Checkout failed before the order could be placed.",
                data={"status": "failed", "order_id": failed_order.order_id, "failure_code": exc.code},
            )
            return {
                "purchase_orders": [failed_order.model_dump(mode="json")],
                "current_node": "checkout_executor",
                "current_phase": "checkout",
                "status": "failed",
                "phase_statuses": _phase_statuses("failed"),
                "checkout_stage": "manual_review",
                "latest_error": str(exc),
            }
        except Exception as exc:
            failed_order = order.model_copy(
                update={
                    "status": "failed",
                    "failure_code": "unknown",
                    "failure_reason": str(exc),
                }
            )
            await emit_run_event(
                run_id=state["run_id"],
                event_type="error",
                phase="checkout",
                node_name="checkout_executor",
                message=str(exc),
                data={"order_id": failed_order.order_id, "failure_code": "unknown"},
            )
            await emit_run_event(
                run_id=state["run_id"],
                event_type="run_completed",
                phase="checkout",
                node_name="checkout_executor",
                message="Checkout failed before the order could be placed.",
                data={"status": "failed", "order_id": failed_order.order_id, "failure_code": "unknown"},
            )
            return {
                "purchase_orders": [failed_order.model_dump(mode="json")],
                "current_node": "checkout_executor",
                "current_phase": "checkout",
                "status": "failed",
                "phase_statuses": _phase_statuses("failed"),
                "checkout_stage": "manual_review",
                "latest_error": str(exc),
            }
        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_completed",
            phase="checkout",
            node_name="checkout_executor",
            message="Checkout completed with an order confirmation.",
            data={
                "order_id": completed_order.order_id,
                "confirmation_id": completed_order.confirmation.confirmation_id if completed_order.confirmation else None,
            },
        )
        return {
            "purchase_orders": [completed_order.model_dump(mode="json")],
            "current_node": "checkout_executor",
            "current_phase": "checkout",
            "status": "running",
            "phase_statuses": _phase_statuses("running"),
            "checkout_stage": "completed",
            "latest_error": None,
        }


@dataclass
class PostCheckoutVerifierNode:
    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        order = PurchaseOrder.model_validate((state.get("purchase_orders") or [])[0])
        if order.status == "failed":
            return {
                "purchase_orders": [order.model_dump(mode="json")],
                "status": "failed",
                "current_node": "post_checkout_verifier",
                "current_phase": "checkout",
                "phase_statuses": _phase_statuses("failed"),
                "checkout_stage": "manual_review",
                "latest_error": order.failure_reason or "Checkout failed.",
            }
        confirmation = order.confirmation
        if confirmation is None:
            await emit_run_event(
                run_id=state["run_id"],
                event_type="error",
                phase="checkout",
                node_name="post_checkout_verifier",
                message=order.failure_reason or "Checkout finished without an order confirmation.",
                data={"order_id": order.order_id, "failure_code": order.failure_code},
            )
            return {
                "status": "failed",
                "current_node": "post_checkout_verifier",
                "current_phase": "checkout",
                "phase_statuses": _phase_statuses("failed"),
                "latest_error": order.failure_reason or "Missing order confirmation.",
            }

        metadata = ContextMetadata(
            node_name="post_checkout_verifier",
            tokens_used=0,
            token_budget=0,
            fields_included=["purchase_orders"],
            fields_dropped=[],
            retrieved_memory_ids=[],
        )
        await emit_run_event(
            run_id=state["run_id"],
            event_type="run_completed",
            phase="checkout",
            node_name="post_checkout_verifier",
            message="Checkout completed successfully.",
            data={"status": "completed", "order_id": order.order_id},
        )
        return {
            "purchase_orders": [order.model_dump(mode="json")],
            "context_metadata": [metadata.model_dump(mode="json")],
            "status": "completed",
            "current_node": "post_checkout_verifier",
            "current_phase": "checkout",
            "phase_statuses": _phase_statuses("completed"),
            "checkout_stage": "completed",
            "latest_error": None,
        }
