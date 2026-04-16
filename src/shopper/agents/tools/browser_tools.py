from __future__ import annotations

import json
import logging
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal, Optional, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from shopper.config import Settings
from shopper.schemas import (
    AppliedCoupon,
    CartBuildResult,
    CartLineItem,
    CheckoutItemEdit,
    CheckoutFailureCode,
    OrderConfirmation,
    PurchaseOrder,
    StandaloneCheckoutRequest,
    StandaloneCheckoutResult,
)
from shopper.services.browser_profile_manager import is_cloud_session_limit_error, stop_active_cloud_browser_sessions

logger = logging.getLogger(__name__)


BrowserAutomationStatusCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


@dataclass(frozen=True)
class _BrowserRetryAttempt:
    label: str
    use_cloud: bool
    disable_cloud_proxy: bool = False
    cloud_proxy_country_code: str | None = None
    status_text: str = ""


class BrowserUseUnavailableError(RuntimeError):
    """Raised when browser-use cannot be executed in the current environment."""


class CheckoutFlowError(RuntimeError):
    """Raised when checkout could not be completed after approval."""

    def __init__(self, message: str, *, code: CheckoutFailureCode = "unknown") -> None:
        super().__init__(message)
        self.code = code


class _BrowserUseCartLine(BaseModel):
    requested_name: str
    requested_quantity: float = Field(ge=0)
    actual_name: str
    actual_quantity: float = Field(ge=0)
    unit: Optional[str] = None
    unit_price: float = Field(default=0, ge=0)
    line_total: float = Field(default=0, ge=0)
    status: str = "added"
    notes: str = ""
    product_url: Optional[str] = None


class _BrowserUseCartSnapshot(BaseModel):
    items: list[_BrowserUseCartLine] = Field(default_factory=list)
    subtotal: float = Field(default=0, ge=0)
    delivery_fee: float = Field(default=0, ge=0)
    total_cost: float = Field(default=0, ge=0)
    cart_url: Optional[str] = None
    notes: list[str] = Field(default_factory=list)


class _BrowserUseCouponSnapshot(BaseModel):
    coupons: list[AppliedCoupon] = Field(default_factory=list)


class _BrowserUseConfirmationSnapshot(BaseModel):
    status: Literal["confirmed", "failed"]
    confirmation_id: Optional[str] = None
    total_cost: float = Field(default=0, ge=0)
    confirmation_url: Optional[str] = None
    message: str = ""
    failure_reason: Optional[str] = None
    failure_code: Optional[CheckoutFailureCode] = None


class CheckoutAutomationBackend(Protocol):
    async def build_cart(self, request: StandaloneCheckoutRequest, artifact_dir: Path) -> CartBuildResult:
        ...

    async def apply_coupons(
        self,
        request: StandaloneCheckoutRequest,
        order: PurchaseOrder,
        artifact_dir: Path,
    ) -> list[AppliedCoupon]:
        ...

    async def complete_checkout(
        self,
        request: StandaloneCheckoutRequest,
        order: PurchaseOrder,
        artifact_dir: Path,
        *,
        task_override: Optional[str] = None,
        status_callback: BrowserAutomationStatusCallback | None = None,
    ) -> OrderConfirmation:
        ...


def _is_chatgpt_execution_target(request: StandaloneCheckoutRequest | PurchaseOrder) -> bool:
    if isinstance(request, PurchaseOrder):
        store = request.store
        start_url = request.store_url
        cart_url = request.cart_url
    else:
        store = request.store.store
        start_url = request.store.start_url
        cart_url = request.store.cart_url

    haystacks = [store or "", start_url or "", cart_url or ""]
    lowered = " ".join(haystacks).lower()
    return "chatgpt" in lowered or "chat.openai.com" in lowered or "chatgpt.com" in lowered


def browser_use_runtime_status() -> tuple[bool, Optional[str]]:
    if tuple(int(part) for part in platform.python_version_tuple()[:2]) < (3, 11):
        return False, "browser-use requires Python 3.11 or newer."

    try:
        import browser_use  # noqa: F401
    except Exception as exc:  # pragma: no cover - depends on runtime install
        return False, f"browser-use is not installed or failed to import: {exc}"

    return True, None


def _normalize_artifact_dir(root: Path, label: str) -> Path:
    artifact_dir = root / label
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


def _normalize_csv_values(value: str | None) -> list[str]:
    if not value:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value.split(","):
        candidate = item.strip().lower()
        if not candidate or candidate in seen:
            continue
        normalized.append(candidate)
        seen.add(candidate)
    return normalized


def _require_browser_use() -> None:
    available, reason = browser_use_runtime_status()
    if not available:
        raise BrowserUseUnavailableError(reason or "browser-use is unavailable.")


async def _emit_browser_status(
    status_callback: BrowserAutomationStatusCallback | None,
    payload: dict[str, Any],
) -> None:
    if status_callback is None:
        return

    result = status_callback(payload)
    if result is not None:
        await result


def _install_cloud_live_url_callback(browser: object, status_callback: BrowserAutomationStatusCallback) -> None:
    """Capture Browser Use Cloud's live viewer URL without changing the agent API."""
    from browser_use.browser.cloud.cloud import CloudBrowserClient

    class LiveUrlCapturingCloudBrowserClient(CloudBrowserClient):
        async def create_browser(self, request, extra_headers=None):  # type: ignore[no-untyped-def]
            response = await super().create_browser(request, extra_headers=extra_headers)
            await _emit_browser_status(
                status_callback,
                {
                    "type": "browser_live_url",
                    "live_url": response.liveUrl,
                    "cloud_browser_session_id": response.id,
                },
            )
            return response

    browser._cloud_browser_client = LiveUrlCapturingCloudBrowserClient()  # type: ignore[attr-defined]


class BrowserUseCheckoutBackend:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _should_use_cloud_proxy(self, request: StandaloneCheckoutRequest) -> bool:
        return not _is_chatgpt_execution_target(request)

    def _uses_cloud_browser(self, request: StandaloneCheckoutRequest) -> bool:
        return self.settings.browser_checkout_use_cloud and self._should_use_cloud_proxy(request)

    def _build_llm(self):
        _require_browser_use()
        from browser_use import ChatAnthropic, ChatBrowserUse, ChatOpenAI

        provider = getattr(self.settings, "browser_checkout_model_provider", "shopper_default")
        if provider == "browser_use":
            return ChatBrowserUse(
                model=self.settings.browser_checkout_model or "bu-latest",
                api_key=self.settings.browser_use_api_key,
            )
        if provider == "openai":
            return ChatOpenAI(
                model=self.settings.browser_checkout_model or self.settings.llm_model,
                api_key=self.settings.openai_api_key,
            )
        if provider == "anthropic":
            return ChatAnthropic(
                model=self.settings.browser_checkout_model or self.settings.resolved_llm_model,
                api_key=self.settings.anthropic_api_key,
            )
        if self.settings.llm_provider == "openai":
            return ChatOpenAI(model=self.settings.llm_model, api_key=self.settings.openai_api_key)
        return ChatAnthropic(model=self.settings.resolved_llm_model, api_key=self.settings.anthropic_api_key)

    def _should_retry_without_proxy(self, exc: Exception) -> bool:
        return self.settings.browser_checkout_use_cloud and self._is_tunnel_failure(exc)

    def _should_retry_after_session_cleanup(self, exc: Exception) -> bool:
        return self.settings.browser_checkout_use_cloud and is_cloud_session_limit_error(exc)

    async def _stop_active_cloud_sessions(self) -> int:
        return await stop_active_cloud_browser_sessions(self.settings)

    def _history_contains_tunnel_failure(self, history: object) -> bool:
        final_result_getter = getattr(history, "final_result", None)
        if callable(final_result_getter):
            try:
                final_result = final_result_getter()
            except Exception:
                final_result = None
            if "err_tunnel_connection_failed" in str(final_result or "").lower():
                return True
        return False

    @staticmethod
    def _is_tunnel_failure(value: object) -> bool:
        return "err_tunnel_connection_failed" in str(value or "").lower()

    def _cloud_retry_attempts(self, request: StandaloneCheckoutRequest) -> list[_BrowserRetryAttempt]:
        if not self._uses_cloud_browser(request):
            return []

        attempts: list[_BrowserRetryAttempt] = []
        primary_country = (self.settings.browser_checkout_cloud_proxy_country_code or "").strip().lower()
        if primary_country:
            attempts.append(
                _BrowserRetryAttempt(
                    label="proxy-fallback",
                    use_cloud=True,
                    disable_cloud_proxy=True,
                    status_text="Cloud proxy failed. Retrying Browser Use Cloud without a proxy...",
                )
            )

        fallback_countries = _normalize_csv_values(self.settings.browser_checkout_cloud_fallback_proxy_country_codes)
        for country_code in fallback_countries:
            if country_code == primary_country:
                continue
            attempts.append(
                _BrowserRetryAttempt(
                    label=f"proxy-{country_code}-fallback",
                    use_cloud=True,
                    cloud_proxy_country_code=country_code,
                    status_text=f"Retrying Browser Use Cloud through the {country_code.upper()} network...",
                )
            )

        if self.settings.browser_checkout_allow_local_fallback:
            attempts.append(
                _BrowserRetryAttempt(
                    label="local-browser-fallback",
                    use_cloud=False,
                    status_text="Cloud browser could not reach this store. Falling back to a local browser window...",
                )
            )

        return attempts

    @staticmethod
    def _infer_checkout_failure(final_result: object) -> tuple[str, CheckoutFailureCode]:
        final_text = str(final_result or "")
        lowered = final_text.lower()
        if "err_tunnel_connection_failed" in lowered:
            return ("The store could not be reached because the Browser Use network tunnel failed.", "checkout_navigation_failed")
        if "no card" in lowered or "payment method" in lowered or "credit card" in lowered:
            return ("No saved payment method was available to complete checkout.", "missing_payment_method")
        if "sign in" in lowered or "log in" in lowered or "login" in lowered:
            return ("Checkout requires a store login before the order can be placed.", "login_required")
        if "delivery slot" in lowered or "timeslot" in lowered or "time slot" in lowered:
            return ("A delivery or pickup slot must be selected before checkout can finish.", "delivery_slot_required")
        if "address" in lowered:
            return ("A delivery address is required before checkout can finish.", "address_required")
        if "captcha" in lowered or "perimeterx" in lowered or "bot" in lowered:
            return ("The store's bot protection interrupted checkout before the order could be placed.", "bot_protection")
        return ("Checkout did not finish and no order confirmation page was captured.", "unknown")

    def _build_browser(
        self,
        request: StandaloneCheckoutRequest,
        artifact_dir: Path,
        allowed_domains: list[str],
        *,
        disable_cloud_proxy: bool = False,
        use_cloud_override: bool | None = None,
        cloud_proxy_country_code_override: str | None = None,
        status_callback: BrowserAutomationStatusCallback | None = None,
    ):
        _require_browser_use()
        from browser_use import Browser

        use_cloud_browser = self._uses_cloud_browser(request) if use_cloud_override is None else use_cloud_override

        if use_cloud_browser and not self.settings.browser_use_api_key:
            raise BrowserUseUnavailableError(
                "BROWSER_USE_API_KEY is required when SHOPPER_BROWSER_CHECKOUT_USE_CLOUD=true."
            )

        cloud_proxy_country_code = None
        if use_cloud_browser and not disable_cloud_proxy and cloud_proxy_country_code_override:
            cloud_proxy_country_code = cloud_proxy_country_code_override
        elif use_cloud_browser and not disable_cloud_proxy and self._should_use_cloud_proxy(request):
            cloud_proxy_country_code = self.settings.browser_checkout_cloud_proxy_country_code or None

        user_data_dir = self.settings.browser_checkout_user_data_dir or None
        if _is_chatgpt_execution_target(request) and not user_data_dir:
            user_data_dir = str(Path(self.settings.checkout_artifacts_dir).parent / "browser_profiles" / "chatgpt")

        browser = Browser(
            headless=request.headless,
            use_cloud=use_cloud_browser,
            cloud_profile_id=self.settings.browser_checkout_cloud_profile_id if use_cloud_browser else None,
            cloud_proxy_country_code=cloud_proxy_country_code,
            cloud_timeout=self.settings.browser_checkout_cloud_timeout_minutes if use_cloud_browser else None,
            user_data_dir=user_data_dir,
            storage_state=self.settings.browser_checkout_storage_state_path or None,
            allowed_domains=allowed_domains or None,
            downloads_path=str(artifact_dir / "downloads"),
            traces_dir=str(artifact_dir / "traces"),
            captcha_solver=self.settings.browser_checkout_captcha_solver,
        )
        if use_cloud_browser and status_callback is not None:
            _install_cloud_live_url_callback(browser, status_callback)
        return browser

    async def _run_agent_once(
        self,
        task: str,
        artifact_dir: Path,
        output_schema,
        request: StandaloneCheckoutRequest,
        *,
        disable_cloud_proxy: bool = False,
        use_cloud_override: bool | None = None,
        cloud_proxy_country_code_override: str | None = None,
        preflight_url: Optional[str] = None,
        status_callback: BrowserAutomationStatusCallback | None = None,
    ):
        _require_browser_use()
        from browser_use import Agent

        browser = self._build_browser(
            request,
            artifact_dir,
            request.store.allowed_domains,
            disable_cloud_proxy=disable_cloud_proxy,
            use_cloud_override=use_cloud_override,
            cloud_proxy_country_code_override=cloud_proxy_country_code_override,
            status_callback=status_callback,
        )
        attempt_uses_cloud = self._uses_cloud_browser(request) if use_cloud_override is None else use_cloud_override
        history_path = artifact_dir / "conversation.json"
        try:
            if preflight_url and attempt_uses_cloud:
                await browser.start()
                await browser.navigate_to(preflight_url)

            agent = Agent(
                task=task,
                llm=self._build_llm(),
                browser=browser,
                output_model_schema=output_schema,
                save_conversation_path=str(history_path),
                max_actions_per_step=4,
                use_vision=True,
                use_judge=True,
                enable_planning=True,
                generate_gif=False,
            )
            history = await agent.run(max_steps=request.max_steps)
        finally:
            await browser.stop()

        return history

    async def _run_agent(
        self,
        task: str,
        artifact_dir: Path,
        output_schema,
        request: StandaloneCheckoutRequest,
        *,
        preflight_url: Optional[str] = None,
        status_callback: BrowserAutomationStatusCallback | None = None,
    ):
        try:
            history = await self._run_agent_once(
                task,
                artifact_dir,
                output_schema,
                request,
                preflight_url=preflight_url,
                status_callback=status_callback,
            )
        except Exception as exc:
            if self._uses_cloud_browser(request) and self._should_retry_after_session_cleanup(exc):
                stopped = await self._stop_active_cloud_sessions()
                logger.warning(
                    "Browser Use cloud session limit reached; stopped %s active sessions and retrying.", stopped
                )
                try:
                    history = await self._run_agent_once(
                        task,
                        artifact_dir,
                        output_schema,
                        request,
                        preflight_url=preflight_url,
                        status_callback=status_callback,
                    )
                except Exception as retry_exc:
                    exc = retry_exc
                else:
                    exc = None

            if exc is None:
                pass
            elif self._uses_cloud_browser(request) and self._should_retry_without_proxy(exc):
                return await self._run_cloud_fallback_attempts(
                    task,
                    artifact_dir,
                    output_schema,
                    request,
                    preflight_url=preflight_url,
                    status_callback=status_callback,
                    original_error=exc,
                )

            if exc is not None:
                raise

        if (
            self._uses_cloud_browser(request)
            and self._history_contains_tunnel_failure(history)
        ):
            logger.warning("Browser Use cloud session reported tunnel failure; starting fallback ladder.")
            return await self._run_cloud_fallback_attempts(
                task,
                artifact_dir,
                output_schema,
                request,
                preflight_url=preflight_url,
                status_callback=status_callback,
                original_error=RuntimeError("Browser Use cloud session reported ERR_TUNNEL_CONNECTION_FAILED."),
            )

        return history

    async def _run_cloud_fallback_attempts(
        self,
        task: str,
        artifact_dir: Path,
        output_schema,
        request: StandaloneCheckoutRequest,
        *,
        preflight_url: Optional[str] = None,
        status_callback: BrowserAutomationStatusCallback | None = None,
        original_error: Exception | None = None,
    ):
        attempts = self._cloud_retry_attempts(request)
        last_error = original_error

        for attempt in attempts:
            logger.warning("Browser checkout fallback attempt: %s", attempt.label)
            await _emit_browser_status(
                status_callback,
                {
                    "type": "browser_attempt",
                    "view_mode": "cloud" if attempt.use_cloud else "local",
                    "proxy_country_code": attempt.cloud_proxy_country_code,
                    "status_text": attempt.status_text,
                    "attempt_label": attempt.label,
                },
            )
            try:
                history = await self._run_agent_once(
                    task,
                    _normalize_artifact_dir(artifact_dir, attempt.label),
                    output_schema,
                    request,
                    disable_cloud_proxy=attempt.disable_cloud_proxy,
                    use_cloud_override=attempt.use_cloud,
                    cloud_proxy_country_code_override=attempt.cloud_proxy_country_code,
                    preflight_url=preflight_url,
                    status_callback=status_callback,
                )
            except Exception as exc:
                last_error = exc
                if attempt.use_cloud and self._should_retry_after_session_cleanup(exc):
                    stopped = await self._stop_active_cloud_sessions()
                    logger.warning(
                        "Browser Use cloud session limit reached during %s; stopped %s active sessions and retrying.",
                        attempt.label,
                        stopped,
                    )
                    try:
                        history = await self._run_agent_once(
                            task,
                            _normalize_artifact_dir(artifact_dir, f"{attempt.label}-session-cleanup"),
                            output_schema,
                            request,
                            disable_cloud_proxy=attempt.disable_cloud_proxy,
                            use_cloud_override=attempt.use_cloud,
                            cloud_proxy_country_code_override=attempt.cloud_proxy_country_code,
                            preflight_url=preflight_url,
                            status_callback=status_callback,
                        )
                    except Exception as retry_exc:
                        last_error = retry_exc
                    else:
                        if attempt.use_cloud and self._history_contains_tunnel_failure(history):
                            last_error = RuntimeError("Browser Use cloud session reported ERR_TUNNEL_CONNECTION_FAILED.")
                            continue
                        return history

                if attempt.use_cloud and self._is_tunnel_failure(exc):
                    continue
                if not attempt.use_cloud and self._is_tunnel_failure(exc):
                    continue
                raise

            if attempt.use_cloud and self._history_contains_tunnel_failure(history):
                last_error = RuntimeError("Browser Use cloud session reported ERR_TUNNEL_CONNECTION_FAILED.")
                continue

            return history

        if last_error is not None:
            raise last_error
        raise CheckoutFlowError(
            "Checkout browser could not reach the merchant after all fallback attempts.",
            code="checkout_navigation_failed",
        )

    async def build_cart(self, request: StandaloneCheckoutRequest, artifact_dir: Path) -> CartBuildResult:
        task = self._build_cart_task(request)
        history = await self._run_agent(
            task,
            artifact_dir,
            _BrowserUseCartSnapshot,
            request,
            preflight_url=request.store.start_url,
        )
        structured = history.get_structured_output(_BrowserUseCartSnapshot)
        if structured is None:
            raise BrowserUseUnavailableError("browser-use finished without a structured cart snapshot.")

        screenshot_paths = [path for path in history.screenshot_paths(return_none_if_not_screenshot=False) if path]
        screenshot_path = screenshot_paths[-1] if screenshot_paths else None
        items = [
            CartLineItem(
                requested_name=item.requested_name,
                requested_quantity=item.requested_quantity,
                actual_name=item.actual_name,
                actual_quantity=item.actual_quantity,
                unit=item.unit,
                unit_price=item.unit_price,
                line_total=item.line_total,
                status=item.status if item.status in {"added", "missing", "substituted", "removed"} else "added",
                notes=item.notes,
                product_url=item.product_url,
            )
            for item in structured.items
        ]
        total_cost = structured.total_cost or round(
            structured.subtotal + structured.delivery_fee,
            2,
        )
        return CartBuildResult(
            store=request.store.store,
            store_url=request.store.start_url,
            items=items,
            subtotal=structured.subtotal,
            delivery_fee=structured.delivery_fee,
            total_cost=total_cost,
            cart_url=structured.cart_url or request.store.cart_url,
            cart_screenshot_path=screenshot_path,
            notes=structured.notes,
            raw_response={"final_result": history.final_result(), "history_path": str(artifact_dir / "conversation.json")},
        )

    async def apply_coupons(
        self,
        request: StandaloneCheckoutRequest,
        order: PurchaseOrder,
        artifact_dir: Path,
    ) -> list[AppliedCoupon]:
        if not order.cart_url and not request.store.cart_url:
            return []

        task = self._build_coupon_task(request, order)
        history = await self._run_agent(
            task,
            artifact_dir,
            _BrowserUseCouponSnapshot,
            request,
            preflight_url=order.cart_url or request.store.cart_url,
        )
        structured = history.get_structured_output(_BrowserUseCouponSnapshot)
        if structured is None:
            return []
        return structured.coupons

    async def complete_checkout(
        self,
        request: StandaloneCheckoutRequest,
        order: PurchaseOrder,
        artifact_dir: Path,
        *,
        task_override: Optional[str] = None,
        status_callback: BrowserAutomationStatusCallback | None = None,
    ) -> OrderConfirmation:
        destination = order.checkout_url or request.store.checkout_url or order.cart_url or request.store.start_url
        task = task_override or self._build_checkout_task(request, order)
        history = await self._run_agent(
            task,
            artifact_dir,
            _BrowserUseConfirmationSnapshot,
            request,
            preflight_url=destination,
            status_callback=status_callback,
        )
        structured = history.get_structured_output(_BrowserUseConfirmationSnapshot)
        if structured is None:
            failure_message, failure_code = self._infer_checkout_failure(history.final_result())
            raise CheckoutFlowError(failure_message, code=failure_code)

        if structured.status != "confirmed" or not structured.confirmation_id:
            raise CheckoutFlowError(
                structured.failure_reason or structured.message or "Checkout did not complete successfully.",
                code=structured.failure_code or "unknown",
            )

        screenshot_paths = [path for path in history.screenshot_paths(return_none_if_not_screenshot=False) if path]
        screenshot_path = screenshot_paths[-1] if screenshot_paths else None
        return OrderConfirmation(
            confirmation_id=structured.confirmation_id,
            total_cost=structured.total_cost,
            confirmation_url=structured.confirmation_url,
            confirmation_screenshot_path=screenshot_path,
            message=structured.message,
        )

    @staticmethod
    def _build_cart_task(request: StandaloneCheckoutRequest) -> str:
        item_lines = "\n".join(
            f"- requested_name: {item.name}; quantity: {item.shopping_quantity or item.quantity}; unit: {item.unit or 'count'}"
            for item in request.items
        )
        return (
            f"You are building a grocery cart for {request.store.store}.\n"
            f"Start at {request.store.start_url}.\n"
            "Add every requested item to the cart using the exact requested quantity whenever possible.\n"
            "Do not complete checkout.\n"
            "If an item is unavailable, keep it in the output with status='missing'.\n"
            "End on the cart page and return structured output only.\n"
            "Requested items:\n"
            f"{item_lines}"
        )

    @staticmethod
    def _build_coupon_task(request: StandaloneCheckoutRequest, order: PurchaseOrder) -> str:
        return (
            f"Review the {request.store.store} cart at {order.cart_url or request.store.cart_url}.\n"
            "Apply any clearly available cart-level coupons that do not change the requested items.\n"
            "Return structured output only."
        )

    @staticmethod
    def _build_checkout_task(request: StandaloneCheckoutRequest, order: PurchaseOrder) -> str:
        destination = order.checkout_url or request.store.checkout_url or order.cart_url or request.store.start_url
        return (
            f"Finish checkout for the prepared {request.store.store} grocery cart.\n"
            f"Continue from {destination}.\n"
            "Place the order only if the cart is already ready for purchase.\n"
            "Do not edit item quantities unless checkout cannot proceed otherwise.\n"
            "Return structured output only.\n"
            "If the order is successfully placed and the confirmation page is visible, set status='confirmed'.\n"
            "If checkout cannot finish, set status='failed' and include a specific failure_reason and failure_code.\n"
            "Use failure_code='missing_payment_method' when there is no saved card or wallet option.\n"
            "Use failure_code='login_required' when the store asks for login.\n"
            "Use failure_code='address_required' when address or store selection is missing.\n"
            "Use failure_code='delivery_slot_required' when a time slot must be chosen.\n"
            "Use failure_code='bot_protection' when CAPTCHA, PerimeterX, or bot protection blocks progress.\n"
            "Do not claim success unless the order confirmation page is clearly visible."
        )


class ChatGPTInstacartCheckoutBackend(BrowserUseCheckoutBackend):
    @staticmethod
    def _build_cart_task(request: StandaloneCheckoutRequest) -> str:
        item_lines = "\n".join(
            f"- {item.name}: {item.shopping_quantity or item.quantity} {item.unit or 'count'}"
            for item in request.items
        )
        return (
            "You are operating ChatGPT and must use the Instacart app inside ChatGPT as the checkout rail.\n"
            f"Start at {request.store.start_url}.\n"
            "If ChatGPT is not signed in, stop and report that login is required.\n"
            "Open a new chat if needed and use the Instacart app.\n"
            "Send a concise request that asks the Instacart app to build a cart for the requested items.\n"
            "Do not place the order.\n"
            "Wait for the app to finish and then capture the final cart summary.\n"
            "Use the current ChatGPT conversation URL as cart_url if no Instacart cart URL is shown.\n"
            "Return structured output only.\n"
            "Requested items:\n"
            f"{item_lines}"
        )

    @staticmethod
    def _build_checkout_task(request: StandaloneCheckoutRequest, order: PurchaseOrder) -> str:
        destination = order.cart_url or request.store.start_url
        return (
            "You are operating ChatGPT and must use the Instacart app inside ChatGPT to finish checkout.\n"
            f"Continue from {destination}.\n"
            "If the conversation is not already open, reopen it and locate the prepared Instacart cart.\n"
            "Confirm the order only if the prepared cart is still available and matches the request.\n"
            "If the cart is missing, the Instacart app is unavailable, or login is required, return status='failed'.\n"
            "If checkout succeeds, return status='confirmed' with the confirmation id, total cost, and confirmation URL if visible.\n"
            "Use failure_code='login_required' when ChatGPT or Instacart requires sign-in.\n"
            "Use failure_code='bot_protection' when ChatGPT or the app blocks progress due to access restrictions.\n"
            "Use failure_code='address_required' when delivery address or store selection is missing.\n"
            "Use failure_code='missing_payment_method' when no payment method is available.\n"
            "Do not claim success unless an order confirmation is clearly visible."
        )

    async def apply_coupons(
        self,
        request: StandaloneCheckoutRequest,
        order: PurchaseOrder,
        artifact_dir: Path,
    ) -> list[AppliedCoupon]:
        return []

    @staticmethod
    def _infer_checkout_failure(final_result: object) -> tuple[str, CheckoutFailureCode]:
        final_text = str(final_result or "")
        lowered = final_text.lower()
        if "instacart app" in lowered and "not available" in lowered:
            return ("The Instacart app was not available inside ChatGPT.", "unknown")
        if "sign in" in lowered or "login" in lowered:
            return ("ChatGPT or the Instacart app requires login before checkout can continue.", "login_required")
        if "payment method" in lowered or "card" in lowered:
            return ("No saved payment method was available in the ChatGPT Instacart flow.", "missing_payment_method")
        if "address" in lowered or "store selection" in lowered:
            return ("The ChatGPT Instacart flow needs an address or store selection before checkout can finish.", "address_required")
        return BrowserUseCheckoutBackend._infer_checkout_failure(final_result)


class CheckoutAutomationRouter:
    def __init__(
        self,
        settings: Settings,
        *,
        merchant_backend: CheckoutAutomationBackend | None = None,
        chatgpt_backend: CheckoutAutomationBackend | None = None,
    ) -> None:
        self.merchant_backend = merchant_backend or BrowserUseCheckoutBackend(settings)
        self.chatgpt_backend = chatgpt_backend or ChatGPTInstacartCheckoutBackend(settings)

    def _backend_for(self, request: StandaloneCheckoutRequest | PurchaseOrder) -> CheckoutAutomationBackend:
        if _is_chatgpt_execution_target(request):
            return self.chatgpt_backend
        return self.merchant_backend

    async def build_cart(self, request: StandaloneCheckoutRequest, artifact_dir: Path) -> CartBuildResult:
        return await self._backend_for(request).build_cart(request, artifact_dir)

    async def apply_coupons(
        self,
        request: StandaloneCheckoutRequest,
        order: PurchaseOrder,
        artifact_dir: Path,
    ) -> list[AppliedCoupon]:
        return await self._backend_for(request).apply_coupons(request, order, artifact_dir)

    async def complete_checkout(
        self,
        request: StandaloneCheckoutRequest,
        order: PurchaseOrder,
        artifact_dir: Path,
        *,
        task_override: Optional[str] = None,
        status_callback: BrowserAutomationStatusCallback | None = None,
    ) -> OrderConfirmation:
        return await self._backend_for(request).complete_checkout(
            request,
            order,
            artifact_dir,
            task_override=task_override,
            status_callback=status_callback,
        )


@dataclass
class BrowserCheckoutAgent:
    settings: Settings
    automation_backend: CheckoutAutomationBackend
    verifier: object
    artifact_root: Path
    max_build_attempts: int = 2

    def __init__(
        self,
        settings: Settings,
        automation_backend: Optional[CheckoutAutomationBackend] = None,
        verifier=None,
        artifact_root: Optional[Path] = None,
    ) -> None:
        from shopper.agents.tools.cart_verifier import CartVerifier

        self.settings = settings
        if automation_backend is not None:
            self.automation_backend = automation_backend
        elif settings.checkout_execution_provider == "browser_use":
            self.automation_backend = BrowserUseCheckoutBackend(settings)
        elif settings.checkout_execution_provider == "chatgpt_instacart":
            self.automation_backend = ChatGPTInstacartCheckoutBackend(settings)
        else:
            self.automation_backend = CheckoutAutomationRouter(settings)
        self.verifier = verifier or CartVerifier()
        self.artifact_root = artifact_root or Path(settings.checkout_artifacts_dir)
        self.max_build_attempts = 2

    def _artifact_dir(self, label: str) -> Path:
        return _normalize_artifact_dir(self.artifact_root, label)

    def _order_from_cart(self, request: StandaloneCheckoutRequest, cart: CartBuildResult, verification) -> PurchaseOrder:
        return PurchaseOrder(
            order_id=f"{request.user_id}-{uuid4().hex[:8]}",
            store=cart.store,
            store_url=cart.store_url,
            channel="online",
            status="awaiting_approval" if verification.passed else "manual_review",
            items=cart.items,
            requested_items=request.items,
            subtotal=cart.subtotal,
            delivery_fee=cart.delivery_fee,
            total_cost=cart.total_cost,
            coupons=cart.coupons,
            verification=verification,
            cart_url=cart.cart_url,
            checkout_url=request.store.checkout_url,
            allowed_domains=request.store.allowed_domains,
            cart_screenshot_path=cart.cart_screenshot_path,
            failure_code=None if verification.passed else "cart_verification_failed",
            failure_reason=None if verification.passed else "Cart verification failed.",
        )

    def _guardrails(
        self,
        order: PurchaseOrder,
        *,
        weekly_budget: Optional[float] = None,
        max_order_total: Optional[float] = None,
    ) -> Optional[str]:
        order_limit = max_order_total or self.settings.checkout_max_order_total_usd
        if order.total_cost > order_limit:
            return f"Cart total ${order.total_cost:.2f} exceeds the per-order guardrail of ${order_limit:.2f}."

        if weekly_budget is not None and order.total_cost > weekly_budget:
            return f"Cart total ${order.total_cost:.2f} exceeds the weekly budget of ${weekly_budget:.2f}."

        return None

    async def prepare_order(
        self,
        request: StandaloneCheckoutRequest,
        *,
        weekly_budget: Optional[float] = None,
        max_order_total: Optional[float] = None,
        artifact_label: Optional[str] = None,
    ) -> PurchaseOrder:
        artifact_dir = self._artifact_dir(artifact_label or f"{request.user_id}-{uuid4().hex[:8]}")
        last_error: Optional[str] = None
        last_order: Optional[PurchaseOrder] = None

        for attempt in range(1, self.max_build_attempts + 1):
            attempt_dir = _normalize_artifact_dir(artifact_dir, f"attempt-{attempt}")
            try:
                cart = await self.automation_backend.build_cart(request, attempt_dir)
                verification = self.verifier.verify_cart(request.items, cart)
                order = self._order_from_cart(request, cart, verification)
                guardrail_error = self._guardrails(
                    order,
                    weekly_budget=weekly_budget,
                    max_order_total=max_order_total,
                )
                if guardrail_error:
                    order.status = "failed"
                    order.failure_code = "budget_guardrail"
                    order.failure_reason = guardrail_error
                    return order
                if verification.passed:
                    return order
                last_order = order
                last_error = order.failure_reason
            except Exception as exc:
                last_error = str(exc)

        if last_order is not None:
            last_order.status = "manual_review"
            last_order.failure_reason = last_error or last_order.failure_reason
            return last_order

        return PurchaseOrder(
            order_id=f"{request.user_id}-{uuid4().hex[:8]}",
            store=request.store.store,
            store_url=request.store.start_url,
            status="manual_review",
            allowed_domains=request.store.allowed_domains,
            requested_items=request.items,
            failure_code="cart_build_failed",
            failure_reason=last_error or "Browser cart build failed.",
        )

    def apply_edits(self, order: PurchaseOrder, edits: list[CheckoutItemEdit]) -> PurchaseOrder:
        edited_order = order.model_copy(deep=True)
        line_by_name = {line.requested_name.lower(): line for line in edited_order.items}
        for edit in edits:
            line = line_by_name.get(edit.requested_name.lower())
            if line is None:
                continue
            if edit.remove:
                line.status = "removed"
                line.actual_quantity = 0
                line.line_total = 0
                continue
            if edit.quantity is not None:
                line.requested_quantity = edit.quantity
                line.actual_quantity = edit.quantity
                line.line_total = round(line.unit_price * edit.quantity, 2)

        edited_order.subtotal = round(
            sum(line.line_total for line in edited_order.items if line.status != "removed"),
            2,
        )
        edited_order.total_cost = round(
            edited_order.subtotal + edited_order.delivery_fee - sum(c.amount for c in edited_order.coupons),
            2,
        )
        return edited_order

    async def complete_order(
        self,
        request: StandaloneCheckoutRequest,
        order: PurchaseOrder,
        *,
        artifact_label: Optional[str] = None,
    ) -> PurchaseOrder:
        if order.status not in {"awaiting_approval", "approved"}:
            raise ValueError("Only approved carts can proceed to checkout.")

        artifact_dir = self._artifact_dir(artifact_label or f"{request.user_id}-{uuid4().hex[:8]}-checkout")
        coupons = await self.automation_backend.apply_coupons(request, order, artifact_dir)
        if coupons:
            order = order.model_copy(
                update={
                    "coupons": coupons,
                    "total_cost": round(order.subtotal + order.delivery_fee - sum(c.amount for c in coupons), 2),
                }
            )

        confirmation = await self.automation_backend.complete_checkout(request, order, artifact_dir)
        return order.model_copy(
            update={
                "status": "purchased",
                "confirmation": confirmation,
                "total_cost": confirmation.total_cost,
                "failure_code": None,
                "failure_reason": None,
            }
        )

    async def run(
        self,
        request: StandaloneCheckoutRequest,
        *,
        weekly_budget: Optional[float] = None,
        max_order_total: Optional[float] = None,
        artifact_label: Optional[str] = None,
    ) -> StandaloneCheckoutResult:
        order = await self.prepare_order(
            request,
            weekly_budget=weekly_budget,
            max_order_total=max_order_total,
            artifact_label=artifact_label,
        )
        if order.status in {"failed", "manual_review"}:
            return StandaloneCheckoutResult(
                order=order,
                status="failed",
                approval_required=False,
                notes=[order.failure_reason or "Checkout preparation failed."],
            )

        if not request.approve:
            return StandaloneCheckoutResult(
                order=order,
                status="awaiting_approval",
                approval_required=True,
                notes=["Cart is ready for human review before purchase."],
            )

        approved_order = order.model_copy(update={"status": "approved"})
        completed = await self.complete_order(
            request,
            approved_order,
            artifact_label=artifact_label,
        )
        return StandaloneCheckoutResult(
            order=completed,
            status="completed" if completed.status == "purchased" else "failed",
            approval_required=False,
            notes=["Checkout completed."] if completed.status == "purchased" else [completed.failure_reason or "Checkout failed."],
        )


def standalone_result_json(result: StandaloneCheckoutResult) -> str:
    return json.dumps(result.model_dump(mode="json"), indent=2)
