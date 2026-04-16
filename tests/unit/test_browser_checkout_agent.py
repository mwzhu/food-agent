from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

from shopper.agents.tools import browser_tools
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

    async def complete_checkout(self, request, order, artifact_dir: Path, *, task_override=None, status_callback=None):
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
        use_cloud_override=None,
        cloud_proxy_country_code_override=None,
        preflight_url=None,
        status_callback=None,
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


def test_browser_use_backend_does_not_pass_cloud_params_when_cloud_disabled(tmp_path: Path, monkeypatch) -> None:
    captured_kwargs = {}

    class FakeBrowser:
        def __init__(self, **kwargs) -> None:
            captured_kwargs.update(kwargs)

    fake_browser_use = types.SimpleNamespace(Browser=FakeBrowser)
    monkeypatch.setitem(sys.modules, "browser_use", fake_browser_use)
    monkeypatch.setattr(browser_tools, "_require_browser_use", lambda: None)

    settings = Settings(
        SHOPPER_APP_ENV="test",
        SHOPPER_CHECKOUT_ARTIFACTS_DIR=str(tmp_path / "artifacts"),
        SHOPPER_BROWSER_CHECKOUT_USE_CLOUD=False,
        SHOPPER_BROWSER_CHECKOUT_CLOUD_PROFILE_ID="profile-123",
        SHOPPER_BROWSER_CHECKOUT_CLOUD_PROXY_COUNTRY_CODE="us",
        SHOPPER_BROWSER_CHECKOUT_CLOUD_TIMEOUT_MINUTES=15,
        BROWSER_USE_API_KEY="test-key",
        LANGSMITH_TRACING=False,
    )
    backend = BrowserUseCheckoutBackend(settings)

    browser = backend._build_browser(_request(), tmp_path / "artifacts", ["demo.example"])

    assert isinstance(browser, FakeBrowser)
    assert captured_kwargs["use_cloud"] is False
    assert captured_kwargs["cloud_profile_id"] is None
    assert captured_kwargs["cloud_proxy_country_code"] is None
    assert captured_kwargs["cloud_timeout"] is None


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
        use_cloud_override=None,
        cloud_proxy_country_code_override=None,
        preflight_url=None,
        status_callback=None,
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


class CountryFallbackBackend(BrowserUseCheckoutBackend):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.calls: list[tuple[bool, object, object, str]] = []

    async def _run_agent_once(
        self,
        task,
        artifact_dir: Path,
        output_schema,
        request,
        *,
        disable_cloud_proxy: bool = False,
        use_cloud_override=None,
        cloud_proxy_country_code_override=None,
        preflight_url=None,
        status_callback=None,
    ):
        self.calls.append(
            (
                disable_cloud_proxy,
                use_cloud_override,
                cloud_proxy_country_code_override,
                artifact_dir.name,
            )
        )
        assert preflight_url == request.store.start_url
        if cloud_proxy_country_code_override == "ca":
            return "country-fallback-ok"
        raise RuntimeError("Navigation failed: net::ERR_TUNNEL_CONNECTION_FAILED")


def test_browser_use_backend_retries_with_fallback_proxy_country(tmp_path: Path) -> None:
    settings = Settings(
        SHOPPER_APP_ENV="test",
        SHOPPER_CHECKOUT_ARTIFACTS_DIR=str(tmp_path / "artifacts"),
        SHOPPER_BROWSER_CHECKOUT_USE_CLOUD=True,
        SHOPPER_BROWSER_CHECKOUT_CLOUD_PROXY_COUNTRY_CODE="us",
        SHOPPER_BROWSER_CHECKOUT_CLOUD_FALLBACK_PROXY_COUNTRY_CODES="ca,uk",
        BROWSER_USE_API_KEY="test-key",
        LANGSMITH_TRACING=False,
    )
    backend = CountryFallbackBackend(settings)

    events = []
    result = asyncio.run(
        backend._run_agent(
            "task",
            tmp_path / "artifacts",
            object,
            _request(),
            preflight_url=_request().store.start_url,
            status_callback=events.append,
        )
    )

    assert result == "country-fallback-ok"
    assert backend.calls == [
        (False, None, None, "artifacts"),
        (True, True, None, "proxy-fallback"),
        (False, True, "ca", "proxy-ca-fallback"),
    ]
    assert [event["attempt_label"] for event in events if event["type"] == "browser_attempt"] == [
        "proxy-fallback",
        "proxy-ca-fallback",
    ]


class LocalFallbackBackend(BrowserUseCheckoutBackend):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.calls: list[tuple[bool, object, object, str]] = []

    async def _run_agent_once(
        self,
        task,
        artifact_dir: Path,
        output_schema,
        request,
        *,
        disable_cloud_proxy: bool = False,
        use_cloud_override=None,
        cloud_proxy_country_code_override=None,
        preflight_url=None,
        status_callback=None,
    ):
        self.calls.append(
            (
                disable_cloud_proxy,
                use_cloud_override,
                cloud_proxy_country_code_override,
                artifact_dir.name,
            )
        )
        assert preflight_url == request.store.start_url
        if use_cloud_override is False:
            return "local-fallback-ok"
        raise RuntimeError("Navigation failed: net::ERR_TUNNEL_CONNECTION_FAILED")


def test_browser_use_backend_falls_back_to_local_browser_after_cloud_attempts(tmp_path: Path) -> None:
    settings = Settings(
        SHOPPER_APP_ENV="test",
        SHOPPER_CHECKOUT_ARTIFACTS_DIR=str(tmp_path / "artifacts"),
        SHOPPER_BROWSER_CHECKOUT_USE_CLOUD=True,
        SHOPPER_BROWSER_CHECKOUT_CLOUD_PROXY_COUNTRY_CODE="us",
        SHOPPER_BROWSER_CHECKOUT_CLOUD_FALLBACK_PROXY_COUNTRY_CODES="ca",
        SHOPPER_BROWSER_CHECKOUT_ALLOW_LOCAL_FALLBACK=True,
        BROWSER_USE_API_KEY="test-key",
        LANGSMITH_TRACING=False,
    )
    backend = LocalFallbackBackend(settings)

    events = []
    request = _request()
    result = asyncio.run(
        backend._run_agent(
            "task",
            tmp_path / "artifacts",
            object,
            request,
            preflight_url=request.store.start_url,
            status_callback=events.append,
        )
    )

    assert result == "local-fallback-ok"
    assert backend.calls == [
        (False, None, None, "artifacts"),
        (True, True, None, "proxy-fallback"),
        (False, True, "ca", "proxy-ca-fallback"),
        (False, False, None, "local-browser-fallback"),
    ]
    assert events[-1]["view_mode"] == "local"


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
        use_cloud_override=None,
        cloud_proxy_country_code_override=None,
        preflight_url=None,
        status_callback=None,
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
