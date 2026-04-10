from __future__ import annotations

import asyncio
from pathlib import Path

from shopper.agents.tools.browser_tools import BrowserCheckoutAgent
from shopper.agents.tools.browser_tools import BrowserUseCheckoutBackend
from shopper.config import Settings
from shopper.schemas import CartBuildResult, CartLineItem, OrderConfirmation, StandaloneCheckoutRequest


class FakeCheckoutBackend:
    def __init__(self, build_results=None, confirmation=None):
        self.build_results = list(build_results or [])
        self.confirmation = confirmation or OrderConfirmation(
            confirmation_id="order-123",
            total_cost=18.0,
            message="Order placed.",
        )

    async def build_cart(self, request, artifact_dir: Path):
        result = self.build_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def apply_coupons(self, request, order, artifact_dir: Path):
        return []

    async def complete_checkout(self, request, order, artifact_dir: Path):
        return self.confirmation


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        SHOPPER_APP_ENV="test",
        SHOPPER_CHECKOUT_ARTIFACTS_DIR=str(tmp_path / "artifacts"),
        LANGSMITH_TRACING=False,
    )


def _request(approve: bool = False) -> StandaloneCheckoutRequest:
    return StandaloneCheckoutRequest(
        user_id="checkout-user",
        store={
            "store": "Demo Store",
            "start_url": "https://demo.example",
        },
        items=[
            {
                "name": "bananas",
                "quantity": 6,
                "unit": "count",
                "category": "produce",
                "already_have": False,
                "shopping_quantity": 6,
                "quantity_in_fridge": 0,
                "source_recipe_ids": [],
            }
        ],
        approve=approve,
        headless=True,
        max_steps=5,
    )


def _cart(quantity: float) -> CartBuildResult:
    return CartBuildResult(
        store="Demo Store",
        store_url="https://demo.example",
        items=[
            CartLineItem(
                requested_name="bananas",
                requested_quantity=6,
                actual_name="bananas",
                actual_quantity=quantity,
                unit="count",
                unit_price=1.5,
                line_total=quantity * 1.5,
                status="added",
            )
        ],
        subtotal=quantity * 1.5,
        delivery_fee=0,
        total_cost=quantity * 1.5,
        cart_url="https://demo.example/cart",
    )


def test_prepare_order_waits_for_approval_when_cart_verifies(tmp_path: Path) -> None:
    agent = BrowserCheckoutAgent(
        _settings(tmp_path),
        automation_backend=FakeCheckoutBackend(build_results=[_cart(6)]),
        artifact_root=tmp_path / "artifacts",
    )

    order = asyncio.run(agent.prepare_order(_request(), weekly_budget=50))

    assert order.status == "awaiting_approval"
    assert order.verification is not None
    assert order.verification.passed is True
    assert order.total_cost == 9.0


def test_prepare_order_falls_back_to_manual_review_after_retries(tmp_path: Path) -> None:
    agent = BrowserCheckoutAgent(
        _settings(tmp_path),
        automation_backend=FakeCheckoutBackend(build_results=[_cart(5), _cart(5)]),
        artifact_root=tmp_path / "artifacts",
    )

    order = asyncio.run(agent.prepare_order(_request(), weekly_budget=50))

    assert order.status == "manual_review"
    assert order.verification is not None
    assert order.verification.passed is False


def test_run_can_complete_checkout_after_explicit_approval(tmp_path: Path) -> None:
    agent = BrowserCheckoutAgent(
        _settings(tmp_path),
        automation_backend=FakeCheckoutBackend(build_results=[_cart(6)]),
        artifact_root=tmp_path / "artifacts",
    )

    result = asyncio.run(agent.run(_request(approve=True), weekly_budget=50))

    assert result.status == "completed"
    assert result.order.status == "purchased"
    assert result.order.confirmation is not None


class RetryBackend(BrowserUseCheckoutBackend):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.disable_cloud_proxy_calls: list[bool] = []

    async def _run_agent_once(
        self,
        task,
        artifact_dir: Path,
        output_schema,
        request,
        *,
        disable_cloud_proxy: bool = False,
        preflight_url=None,
    ):
        self.disable_cloud_proxy_calls.append(disable_cloud_proxy)
        assert preflight_url == request.store.start_url
        if not disable_cloud_proxy:
            raise RuntimeError("Navigation failed: net::ERR_TUNNEL_CONNECTION_FAILED")
        return "fallback-ok"


def test_browser_use_backend_retries_without_proxy_on_tunnel_failure(tmp_path: Path) -> None:
    settings = Settings(
        SHOPPER_APP_ENV="test",
        SHOPPER_CHECKOUT_ARTIFACTS_DIR=str(tmp_path / "artifacts"),
        SHOPPER_BROWSER_CHECKOUT_USE_CLOUD=True,
        SHOPPER_BROWSER_CHECKOUT_CLOUD_PROXY_COUNTRY_CODE="us",
        BROWSER_USE_API_KEY="test-key",
        LANGSMITH_TRACING=False,
    )
    backend = RetryBackend(settings)

    request = _request()
    result = asyncio.run(
        backend._run_agent("task", tmp_path / "artifacts", object, request, preflight_url=request.store.start_url)
    )

    assert result == "fallback-ok"
    assert backend.disable_cloud_proxy_calls == [False, True]


class FakeHistory:
    def __init__(self, final_result_text: str) -> None:
        self._final_result_text = final_result_text

    def final_result(self) -> str:
        return self._final_result_text


class ResultRetryBackend(BrowserUseCheckoutBackend):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.disable_cloud_proxy_calls: list[bool] = []

    async def _run_agent_once(
        self,
        task,
        artifact_dir: Path,
        output_schema,
        request,
        *,
        disable_cloud_proxy: bool = False,
        preflight_url=None,
    ):
        self.disable_cloud_proxy_calls.append(disable_cloud_proxy)
        assert preflight_url == request.store.start_url
        if not disable_cloud_proxy:
            return FakeHistory('{"notes":["ERR_TUNNEL_CONNECTION_FAILED"]}')
        return "fallback-ok"


def test_browser_use_backend_retries_without_proxy_on_tunnel_result(tmp_path: Path) -> None:
    settings = Settings(
        SHOPPER_APP_ENV="test",
        SHOPPER_CHECKOUT_ARTIFACTS_DIR=str(tmp_path / "artifacts"),
        SHOPPER_BROWSER_CHECKOUT_USE_CLOUD=True,
        SHOPPER_BROWSER_CHECKOUT_CLOUD_PROXY_COUNTRY_CODE="us",
        BROWSER_USE_API_KEY="test-key",
        LANGSMITH_TRACING=False,
    )
    backend = ResultRetryBackend(settings)

    request = _request()
    result = asyncio.run(
        backend._run_agent("task", tmp_path / "artifacts", object, request, preflight_url=request.store.start_url)
    )

    assert result == "fallback-ok"
    assert backend.disable_cloud_proxy_calls == [False, True]


class SessionLimitRetryBackend(BrowserUseCheckoutBackend):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.attempts = 0
        self.cleanup_calls = 0

    async def _stop_active_cloud_sessions(self) -> int:
        self.cleanup_calls += 1
        return 3

    async def _run_agent_once(
        self,
        task,
        artifact_dir: Path,
        output_schema,
        request,
        *,
        disable_cloud_proxy: bool = False,
        preflight_url=None,
    ):
        self.attempts += 1
        assert disable_cloud_proxy is False
        assert preflight_url == request.store.start_url
        if self.attempts == 1:
            raise RuntimeError("HTTP 429 - Free plan limit: 3 concurrent sessions reached.")
        return "cleanup-retry-ok"


def test_browser_use_backend_stops_active_sessions_and_retries_on_cloud_limit(tmp_path: Path) -> None:
    settings = Settings(
        SHOPPER_APP_ENV="test",
        SHOPPER_CHECKOUT_ARTIFACTS_DIR=str(tmp_path / "artifacts"),
        SHOPPER_BROWSER_CHECKOUT_USE_CLOUD=True,
        BROWSER_USE_API_KEY="test-key",
        LANGSMITH_TRACING=False,
    )
    backend = SessionLimitRetryBackend(settings)

    request = _request()
    result = asyncio.run(
        backend._run_agent("task", tmp_path / "artifacts", object, request, preflight_url=request.store.start_url)
    )

    assert result == "cleanup-retry-ok"
    assert backend.cleanup_calls == 1
    assert backend.attempts == 2
